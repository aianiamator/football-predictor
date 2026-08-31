"""SQLite store plus static JSON publishing.

Architecture
------------
    engine  ->  SQLite (data/forecasts.db, on the Hetzner box)
                  |
                  +-> derived static JSON  ->  Cloudflare  ->  app

The database is the durable record. The app never talks to it. Instead the
engine writes small, pre-shaped JSON files that Cloudflare serves from the
edge, which is why the frontend carries no API key of any kind.

Two guarantees this module exists to provide:

  1. A forecast for a match that has already been settled is immutable.
     Enforced by a trigger in schema.sql, and by the WHERE clause on the
     upsert, so a re-run cannot quietly rewrite history.
  2. JSON files are written atomically (temp file then rename), so a reader
     can never observe a half-written file mid-publish.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .performance import SCORED, performance

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("FORECAST_DB", ROOT / "data" / "forecasts.db"))
SCHEMA_PATH = ROOT / "schema.sql"

# Only the fields the app actually renders. Everything else stays in the
# database. Bytes matter: the audience is on metered mobile data.
LIST_FIELDS = [
    "id",
    "league_code", "league", "date", "kickoff_utc",
    "home_team", "away_team",
    "home_win_pct", "draw_pct", "away_win_pct",
    "confidence_stars", "confidence_colour",
    "model_pick", "confidence_band", "margin_band", "confidence_margin",
    "summary_key", "summary_args", "summary",
]
DETAIL_FIELDS = LIST_FIELDS + [
    "over_2_5_pct", "clean_sheet_home_pct", "clean_sheet_away_pct",
    "expected_goals_home", "expected_goals_away",
    "likely_score", "likely_scorelines",
]

FORECAST_FIELDS = [
    "league", "country", "kickoff", "kickoff_utc",
    "home_win_pct", "draw_pct", "away_win_pct", "over_2_5_pct",
    "clean_sheet_home_pct", "clean_sheet_away_pct",
    "expected_goals_home", "expected_goals_away",
    "likely_score", "likely_scorelines",
    "confidence", "confidence_stars", "confidence_colour",
    "summary", "summary_key", "summary_args",
    "model_pick", "confidence_band", "margin_band", "confidence_margin",
    "model_version",
    "generated_at",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open the store, creating and migrating it if needed."""
    path = Path(path) if path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode = WAL")
    conn.execute("pragma foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _migrate(conn)
    conn.commit()
    return conn


# Columns added after the first databases were created. "create table if not
# exists" will not add a column to a table that already exists, so they are
# applied here instead. Purely additive: no column is ever dropped or renamed,
# and no stored forecast is touched.
_ADDED_COLUMNS = {
    "model_version": "text",
    "confidence_margin": "real",
    "confidence_band": "text",
    "margin_band": "text",
    "model_pick": "text",
    "fixture_status": "text default 'pending'",
    "actual_result": "text",
    "brier_score": "real",
}


def _migrate(conn: sqlite3.Connection) -> list[str]:
    """Add any missing columns. Safe to run on every connect."""
    have = {r[1] for r in conn.execute("pragma table_info(predictions)")}
    added = []
    for name, decl in _ADDED_COLUMNS.items():
        if name not in have:
            conn.execute(f"alter table predictions add column {name} {decl}")
            added.append(name)
    if added:
        # Existing rows predate fixture_status; anything already scored is
        # finished by definition, everything else is still pending.
        conn.execute("update predictions set fixture_status = "
                     "case when was_correct is not null then 'finished' else 'pending' end "
                     "where fixture_status is null")

    _backfill_decisions(conn)
    return added


def _backfill_decisions(conn: sqlite3.Connection) -> int:
    """Derive the decision fields for forecasts that predate the decision layer.

    This does NOT alter a single forecast. The three percentages were locked
    when the forecast was published; model_pick, confidence_band, margin_band
    and confidence_margin are a deterministic function of those same numbers,
    so computing them now yields exactly what the engine would have written at
    the time. Without it, forecasts made before the layer existed would settle
    into the overall hit rate but be invisible in the confidence breakdown -
    silently biasing the very analysis those bands exist to support.

    model_version is deliberately NOT backfilled. Which engine produced an old
    forecast cannot be recovered from the stored row, and stamping a guess onto
    it would be exactly the kind of quiet rewriting of history this store is
    built to prevent. Those rows report as "pre-1.1.0".
    """
    from .run import decide   # imported here to avoid a circular import

    rows = conn.execute(
        "select id, home_win_pct, draw_pct, away_win_pct from predictions "
        "where model_pick is null and home_win_pct is not null"
    ).fetchall()
    for r in rows:
        d = decide(r["home_win_pct"], r["draw_pct"], r["away_win_pct"])
        conn.execute(
            "update predictions set model_pick=?, confidence_band=?, "
            "margin_band=?, confidence_margin=? where id=?",
            (d["model_pick"], d["confidence_band"], d["margin_band"],
             d["confidence_margin"], r["id"]),
        )
    if rows:
        conn.commit()
    return len(rows)


def upsert_predictions(conn: sqlite3.Connection, rows: list[dict]) -> dict:
    """Insert new forecasts; refresh existing ones only while unsettled.

    Returns counts of what happened. A fixture that has already been settled
    is left completely alone - the refreshed forecast is discarded, not
    applied, because rewriting a scored forecast would falsify the track
    record.
    """
    if not rows:
        return {"inserted": 0, "refreshed": 0, "frozen": 0}

    now = _now()
    inserted = refreshed = frozen = 0

    for r in rows:
        key = (r["league_code"], r["date"], r["home_team"], r["away_team"])
        existing = conn.execute(
            "select id, was_correct from predictions "
            "where league_code=? and date=? and home_team=? and away_team=?", key
        ).fetchone()

        if existing is not None and existing["was_correct"] is not None:
            frozen += 1
            continue

        payload = dict(r)
        payload["likely_scorelines"] = json.dumps(r.get("likely_scorelines", []),
                                                  separators=(",", ":"))
        payload["summary_args"] = json.dumps(r.get("summary_args", {}),
                                             separators=(",", ":"))
        if existing is None:
            payload["first_published_at"] = now
            cols = ["league_code", "date", "home_team", "away_team",
                    "first_published_at"] + FORECAST_FIELDS
            conn.execute(
                f"insert into predictions ({','.join(cols)}) "
                f"values ({','.join('?' * len(cols))})",
                [payload.get(c) for c in cols],
            )
            inserted += 1
        else:
            sets = ",".join(f"{c}=?" for c in FORECAST_FIELDS)
            conn.execute(
                f"update predictions set {sets} where id=? and was_correct is null",
                [payload.get(c) for c in FORECAST_FIELDS] + [existing["id"]],
            )
            refreshed += 1

    conn.commit()
    return {"inserted": inserted, "refreshed": refreshed, "frozen": frozen}


def upsert_ratings(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    now = _now()
    conn.executemany(
        "insert into team_ratings (league_code, league, team, attack, defence, overall, updated_at) "
        "values (?,?,?,?,?,?,?) "
        "on conflict(league_code, team) do update set "
        "attack=excluded.attack, defence=excluded.defence, "
        "overall=excluded.overall, updated_at=excluded.updated_at",
        [(r["league_code"], r["league"], r["team"], r["attack"],
          r["defence"], r["overall"], now) for r in rows],
    )
    conn.commit()
    return len(rows)


def settle(conn: sqlite3.Connection, league_code: str, date: str,
           home_team: str, away_team: str,
           home_goals: int, away_goals: int) -> bool:
    """Record a finished match's result. Never touches the forecast itself.

    Scoring uses the model_pick STORED with the forecast, not a fresh argmax,
    so a later change to the decision rule cannot retroactively re-grade
    history. Ties are recorded and Brier-scored but deliberately left
    unscored for accuracy: picking one of two indistinguishable outcomes and
    then calling it right or wrong would move the hit rate on luck alone.
    """
    row = conn.execute(
        "select id, home_win_pct, draw_pct, away_win_pct, model_pick, fixture_status "
        "from predictions where league_code=? and date=? and home_team=? and away_team=?",
        (league_code, date, home_team, away_team),
    ).fetchone()
    if row is None or row["fixture_status"] == "finished":
        return False

    if home_goals > away_goals:
        actual, idx = "HOME", 0
    elif home_goals < away_goals:
        actual, idx = "AWAY", 2
    else:
        actual, idx = "DRAW", 1

    # Brier score for this single match: squared error against the one-hot
    # outcome, summed over the three possibilities. 0 is perfect, 2 the worst
    # possible. Bounded, so one confident miss cannot dominate an average.
    p = [row["home_win_pct"] / 100.0, row["draw_pct"] / 100.0, row["away_win_pct"] / 100.0]
    onehot = [0.0, 0.0, 0.0]
    onehot[idx] = 1.0
    brier = sum((pi - oi) ** 2 for pi, oi in zip(p, onehot))

    pick = row["model_pick"]
    if pick and pick != "TIE":
        correct = 1 if {"H": "HOME", "D": "DRAW", "A": "AWAY"}[pick] == actual else 0
    elif pick == "TIE":
        correct = None          # deliberately unscored, see docstring
    else:
        # Forecast predates the decision layer; fall back to the argmax that
        # was in force when it was published.
        pcts = {"HOME": row["home_win_pct"], "DRAW": row["draw_pct"], "AWAY": row["away_win_pct"]}
        correct = 1 if max(pcts, key=pcts.get) == actual else 0

    conn.execute(
        "update predictions set fixture_status='finished', actual_home_goals=?, "
        "actual_away_goals=?, actual_result=?, was_correct=?, brier_score=?, "
        "settled_at=? where id=?",
        (home_goals, away_goals, actual, correct, round(brier, 6), _now(), row["id"]),
    )
    conn.commit()
    return True


def mark_not_played(conn: sqlite3.Connection, league_code: str, date: str,
                    home_team: str, away_team: str, status: str) -> bool:
    """Record that a fixture will not produce a result.

    Postponed, cancelled, abandoned and void matches must never count toward
    accuracy in either direction - they are not wrong forecasts, they are
    forecasts of a match that did not happen. was_correct stays NULL and the
    status records why, so they leave the pending queue without polluting the
    hit rate.
    """
    allowed = {"postponed", "cancelled", "abandoned", "void"}
    if status not in allowed:
        raise ValueError(f"status must be one of {sorted(allowed)}, got {status!r}")

    cur = conn.execute(
        "update predictions set fixture_status=?, settled_at=? "
        "where league_code=? and date=? and home_team=? and away_team=? "
        "and fixture_status != 'finished'",
        (status, _now(), league_code, date, home_team, away_team),
    )
    conn.commit()
    return cur.rowcount > 0


def _atomic_write(path: Path, text: str) -> None:
    """Write via temp file + rename so a reader never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _row_to_dict(row: sqlite3.Row, fields: list[str]) -> dict:
    out = {}
    for f in fields:
        v = row[f]
        if f in ("likely_scorelines", "summary_args") and v:
            v = json.loads(v)
        out[f] = v
    return out


def publish_json(conn: sqlite3.Connection, out_dir: Path, limit: int = 100) -> dict:
    """Write the static files the app fetches.

    predictions.json   upcoming fixtures from today onward, newest first
    track-record.json  per-league accuracy plus the last 20 settled matches
    meta.json          publish timestamp, for the app's cache freshness check
    """
    out_dir = Path(out_dir)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    now_iso = now.isoformat()

    # Filter on KICK-OFF, not calendar date. A match at 10:15 is not "upcoming"
    # at 23:00 the same evening, but a date-only filter keeps it in the list all
    # day. Fall back to the date when no kick-off time was published.
    upcoming = conn.execute(
        f"select {','.join(DETAIL_FIELDS)} from predictions "
        "where fixture_status = 'pending' and ("
        "  (kickoff_utc is not null and kickoff_utc >= ?) or "
        "  (kickoff_utc is null and date >= ?)) "
        "order by coalesce(kickoff_utc, date) asc limit ?",
        (now_iso, today, limit),
    ).fetchall()
    predictions = [_row_to_dict(r, DETAIL_FIELDS) for r in upcoming]

    by_league = [dict(r) for r in conn.execute(
        "select * from accuracy_record order by accuracy_pct desc").fetchall()]

    recent = conn.execute(
        "select league_code, league, date, home_team, away_team, "
        "home_win_pct, draw_pct, away_win_pct, model_pick, confidence_band, "
        "actual_home_goals, actual_away_goals, actual_result, was_correct "
        "from predictions where fixture_status = 'finished' "
        "order by date desc, id desc limit 20"
    ).fetchall()

    # Played, but the results feed has not caught up yet. Publishing these is a
    # deliberate honesty measure: without it a match simply vanishes between
    # being forecast and being scored, and a sceptical reader cannot tell the
    # difference between "waiting" and "quietly dropped because we got it
    # wrong". The forecast shown here is already frozen in the store.
    awaiting = conn.execute(
        "select league_code, league, date, home_team, away_team, "
        "home_win_pct, draw_pct, away_win_pct "
        "from predictions where fixture_status = 'pending' and ("
        "  (kickoff_utc is not null and kickoff_utc < ?) or "
        "  (kickoff_utc is null and date < ?)) "
        "order by coalesce(kickoff_utc, date) desc, id desc limit 20",
        (now_iso, today),
    ).fetchall()

    # The list above is capped, but the COUNT must be the true total. Showing
    # "waiting (20)" while 35 are actually waiting would understate exactly the
    # thing this section exists to be honest about.
    awaiting_total = conn.execute(
        "select count(*) from predictions where fixture_status = 'pending' and ("
        "  (kickoff_utc is not null and kickoff_utc < ?) or "
        "  (kickoff_utc is null and date < ?))",
        (now_iso, today),
    ).fetchone()[0]

    totals = conn.execute(
        "select count(*) n, sum(case when was_correct=1 then 1 else 0 end) hits "
        f"from predictions where {SCORED}").fetchone()
    n_settled = totals["n"] or 0
    hits = totals["hits"] or 0

    track = {
        "overall": {
            "matches_settled": n_settled,
            "accuracy_pct": round(100.0 * hits / n_settled, 1) if n_settled else None,
        },
        "by_league": by_league,
        # The full analytics block: confidence bands, picked outcome, league,
        # calibration, baselines and model versions. Computed in SQL from the
        # stored record, so it costs nothing and cannot disagree with the data.
        "performance": performance(conn),
        "recent": [dict(r) for r in recent],
        "awaiting": [dict(r) for r in awaiting],
        "awaiting_total": int(awaiting_total),
    }

    # The league registry travels with meta.json so the app can render a flag
    # and a name for any league without hard-coding a copy of the list.
    from .data import CORE_LEAGUES, LEAGUES
    leagues = [{"code": c, "name": LEAGUES[c][0],
                "country": LEAGUES[c][1], "flag": LEAGUES[c][2]}
               for c in CORE_LEAGUES if c in LEAGUES]

    published_at = _now()
    _atomic_write(out_dir / "predictions.json",
                  json.dumps(predictions, separators=(",", ":"), ensure_ascii=False))
    _atomic_write(out_dir / "track-record.json",
                  json.dumps(track, separators=(",", ":"), ensure_ascii=False))
    _atomic_write(out_dir / "meta.json",
                  json.dumps({"published_at": published_at,
                              "upcoming": len(predictions),
                              "settled": n_settled,
                              "awaiting": int(awaiting_total),
                              "leagues": leagues},
                             separators=(",", ":"), ensure_ascii=False))

    return {"upcoming": len(predictions), "settled": n_settled,
            "awaiting": int(awaiting_total), "leagues": len(by_league),
            "published_at": published_at}


def stats(conn: sqlite3.Connection) -> dict:
    p = conn.execute("select count(*) n from predictions").fetchone()["n"]
    s = conn.execute("select count(*) n from predictions where was_correct is not null").fetchone()["n"]
    t = conn.execute("select count(*) n from team_ratings").fetchone()["n"]
    return {"predictions": p, "settled": s, "team_ratings": t}
