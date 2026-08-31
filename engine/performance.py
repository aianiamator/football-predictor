"""Performance analytics computed from the stored record.

Everything here is derived from rows in `predictions` - no API calls, no model
re-runs, no LLM. It is ordinary SQL and arithmetic, which is why it costs
nothing to recompute on every publish.

Two rules shape the whole module:

  1. Only FINISHED matches count. A postponed or abandoned fixture is not a
     wrong forecast, it is a forecast of a match that never happened, so it is
     excluded from every rate rather than counted against us.
  2. Every rate travels with its sample size. "100% accurate" over three
     matches is noise, and presenting it without the denominator would be the
     most misleading thing this product could do.
"""
from __future__ import annotations

import sqlite3

# Only rows in this state are eligible for scoring.
SCORED = "fixture_status = 'finished' and was_correct is not null"

# How much weight a sample deserves. Wording is deliberately cautious at the
# small end - a good early run is far more likely to be luck than skill.
SAMPLE_BANDS = [
    (500, "larger_sample"),
    (100, "developing"),
    (30, "early"),
    (0, "very_small"),
]

CONFIDENCE_ORDER = ["high", "strong", "moderate", "low"]
PICK_LABEL = {"H": "home", "D": "draw", "A": "away"}

# Buckets for the calibration table. A forecast's top probability lands in one
# of these, and we then ask how often that forecast was actually right.
PROB_BUCKETS = [(0, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]


def sample_band(n: int) -> str:
    return next(label for floor, label in SAMPLE_BANDS if n >= floor)


def _rate(correct: int, total: int) -> float | None:
    return round(100.0 * correct / total, 1) if total else None


def _bucket(rows) -> dict:
    """Collapse (correct, total, brier_sum) rows into a reportable block."""
    total = len(rows)
    correct = sum(r["was_correct"] for r in rows)
    briers = [r["brier_score"] for r in rows if r["brier_score"] is not None]
    return {
        "completed": total,
        "correct": correct,
        "incorrect": total - correct,
        "hit_rate": _rate(correct, total),
        "brier": round(sum(briers) / len(briers), 4) if briers else None,
        "sample_band": sample_band(total),
    }


def performance(conn: sqlite3.Connection) -> dict:
    """The full analytics payload published to the app."""
    scored = conn.execute(
        f"select league_code, league, model_pick, confidence_band, was_correct, "
        f"brier_score, home_win_pct, draw_pct, away_win_pct, actual_result, "
        f"model_version from predictions where {SCORED}"
    ).fetchall()

    counts = dict(conn.execute(
        "select fixture_status, count(*) from predictions group by 1").fetchall())
    ties = conn.execute(
        "select count(*) from predictions where fixture_status='finished' "
        "and was_correct is null").fetchone()[0]
    not_played = sum(counts.get(k, 0) for k in
                     ("postponed", "cancelled", "abandoned", "void"))

    overall = _bucket(scored)
    overall.update({
        "total_forecasts": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "not_played": not_played,
        "unscored_ties": ties,
    })

    # --- by confidence band: does a higher stated probability actually win
    #     more often? This is the question the bands exist to answer, and it
    #     stays unanswered until the samples are large enough to mean anything.
    by_confidence = []
    for band in CONFIDENCE_ORDER:
        rows = [r for r in scored if r["confidence_band"] == band]
        if rows:
            by_confidence.append({"band": band, **_bucket(rows)})

    # --- by what was picked. Draws are the hard case and deserve their own line.
    by_outcome = []
    for key, label in PICK_LABEL.items():
        rows = [r for r in scored if r["model_pick"] == key]
        if rows:
            by_outcome.append({"pick": label, **_bucket(rows)})

    # --- by league
    by_league = []
    seen = {}
    for r in scored:
        seen.setdefault((r["league_code"], r["league"]), []).append(r)
    for (code, name), rows in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        by_league.append({"league_code": code, "league": name, **_bucket(rows)})

    # --- calibration: when the model says 70%, does it happen 70% of the time?
    calibration = []
    for lo, hi in PROB_BUCKETS:
        rows = [r for r in scored
                if lo <= max(r["home_win_pct"], r["draw_pct"], r["away_win_pct"]) < hi]
        if not rows:
            continue
        avg_p = sum(max(r["home_win_pct"], r["draw_pct"], r["away_win_pct"])
                    for r in rows) / len(rows)
        correct = sum(r["was_correct"] for r in rows)
        calibration.append({
            "band": f"{lo}-{hi - 1}%",
            "predictions": len(rows),
            "correct": correct,
            "actual_rate": _rate(correct, len(rows)),
            "average_predicted": round(avg_p, 1),
            "gap": round(_rate(correct, len(rows)) - avg_p, 1) if rows else None,
            "sample_band": sample_band(len(rows)),
        })

    # --- baselines on the SAME matches, so the comparison is fair.
    #     "Always home" is the honest bar: it needs no model at all.
    baselines = {}
    if scored:
        n = len(scored)
        home_hits = sum(1 for r in scored if r["actual_result"] == "HOME")
        baselines["always_home"] = {
            "completed": n, "correct": home_hits, "hit_rate": _rate(home_hits, n),
        }
        # Climatology: the league's own base rates as a flat forecast. Its Brier
        # is the number a real model has to beat to be worth anything.
        rates = {k: sum(1 for r in scored if r["actual_result"] == k) / n
                 for k in ("HOME", "DRAW", "AWAY")}
        b = 0.0
        for r in scored:
            for k, i in (("HOME", 0), ("DRAW", 1), ("AWAY", 2)):
                b += (rates[k] - (1.0 if r["actual_result"] == k else 0.0)) ** 2
        baselines["base_rates"] = {"completed": n, "brier": round(b / n, 4)}
        if overall["brier"] is not None:
            baselines["model_vs_base_rates_brier"] = round(
                baselines["base_rates"]["brier"] - overall["brier"], 4)
        baselines["model_vs_always_home_points"] = (
            round(overall["hit_rate"] - baselines["always_home"]["hit_rate"], 1)
            if overall["hit_rate"] is not None else None)

    versions = dict(conn.execute(
        "select coalesce(model_version,'pre-1.1.0'), count(*) from predictions "
        "group by 1").fetchall())

    return {
        "overall": overall,
        "by_confidence": by_confidence,
        "by_outcome": by_outcome,
        "by_league": by_league,
        "calibration": calibration,
        "baselines": baselines,
        "model_versions": versions,
    }
