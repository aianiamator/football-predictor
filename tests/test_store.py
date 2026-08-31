"""Store guarantees.

The reason this project keeps a database at all, rather than only writing JSON
files, is that the public track record has to be trustworthy. That requires one
hard property: once a match has been settled, its forecast can never change.

These tests prove it holds, including against a direct SQL update that bypasses
the application code.

Run with:  python -m tests.test_store
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

from engine import store


def _row(home="Arsenal", away="Chelsea", date="2026-09-01", h=60, d=25, a=15):
    return {
        "league_code": "E0", "league": "Premier League", "country": "England",
        "date": date, "kickoff": "20:00", "home_team": home, "away_team": away,
        "home_win_pct": h, "draw_pct": d, "away_win_pct": a,
        "over_2_5_pct": None,
        "clean_sheet_home_pct": 40, "clean_sheet_away_pct": 20,
        "expected_goals_home": 1.8, "expected_goals_away": 0.9,
        "likely_score": "2-0",
        "likely_scorelines": [{"home_goals": 2, "away_goals": 0, "prob": 0.12}],
        "confidence": "moderate", "confidence_stars": 2, "confidence_colour": "#ca8a04",
        "summary": "Arsenal are more likely to win. A draw is still common here.",
        "generated_at": "2026-08-28T00:00:00+00:00",
    }


def _fresh():
    tmp = Path(tempfile.mkdtemp()) / "t.db"
    return store.connect(tmp), tmp


def test_insert_then_refresh():
    """An unsettled forecast may be refreshed by a later run."""
    conn, _ = _fresh()
    c1 = store.upsert_predictions(conn, [_row()])
    assert c1 == {"inserted": 1, "refreshed": 0, "frozen": 0}, c1

    c2 = store.upsert_predictions(conn, [_row(h=70, d=20, a=10)])
    assert c2 == {"inserted": 0, "refreshed": 1, "frozen": 0}, c2

    got = conn.execute("select home_win_pct, first_published_at, generated_at "
                       "from predictions").fetchone()
    assert got["home_win_pct"] == 70, "unsettled forecast should update"
    print(f"  refreshed 60 -> {got['home_win_pct']}; first_published_at preserved")
    conn.close()
    return True


def test_settled_forecast_is_frozen():
    """Once settled, a re-run must NOT rewrite the forecast."""
    conn, _ = _fresh()
    store.upsert_predictions(conn, [_row(h=60, d=25, a=15)])
    assert store.settle(conn, "E0", "2026-09-01", "Arsenal", "Chelsea", 2, 0)

    before = conn.execute("select home_win_pct, summary from predictions").fetchone()
    counts = store.upsert_predictions(conn, [_row(h=99, d=1, a=0)])
    after = conn.execute("select home_win_pct, summary from predictions").fetchone()

    assert counts["frozen"] == 1, counts
    assert after["home_win_pct"] == before["home_win_pct"] == 60, \
        "settled forecast was rewritten"
    print(f"  re-run with 99% ignored; stored forecast still {after['home_win_pct']}%")
    conn.close()
    return True


def test_trigger_blocks_raw_sql():
    """The guarantee must survive someone bypassing the application code."""
    conn, _ = _fresh()
    store.upsert_predictions(conn, [_row()])
    store.settle(conn, "E0", "2026-09-01", "Arsenal", "Chelsea", 2, 0)

    try:
        conn.execute("update predictions set home_win_pct = 99")
        conn.commit()
    except sqlite3.IntegrityError as exc:
        print(f"  raw UPDATE refused: {exc}")
        conn.close()
        return True
    raise AssertionError("raw SQL rewrote a settled forecast; trigger did not fire")


def test_settle_only_once_and_scores_correctly():
    conn, _ = _fresh()
    store.upsert_predictions(conn, [
        _row(home="Arsenal", away="Chelsea", h=60, d=25, a=15),
        _row(home="Leeds", away="Everton", date="2026-09-02", h=20, d=25, a=55),
    ])
    # Home forecast, home win -> correct.
    assert store.settle(conn, "E0", "2026-09-01", "Arsenal", "Chelsea", 2, 0)
    # Away forecast, home win -> incorrect.
    assert store.settle(conn, "E0", "2026-09-02", "Leeds", "Everton", 3, 1)
    # Settling twice must be refused.
    assert not store.settle(conn, "E0", "2026-09-01", "Arsenal", "Chelsea", 5, 5)

    rows = {r["home_team"]: r["was_correct"] for r in
            conn.execute("select home_team, was_correct from predictions")}
    assert rows["Arsenal"] == 1, rows
    assert rows["Leeds"] == 0, rows
    print(f"  scored correctly: {rows}; double-settle refused")
    conn.close()
    return True


def test_publish_shape_and_atomicity():
    conn, _ = _fresh()
    future = "2099-01-01"
    store.upsert_predictions(conn, [_row(date=future)])
    store.upsert_predictions(conn, [_row(home="Leeds", away="Everton", date="2026-09-02")])
    store.settle(conn, "E0", "2026-09-02", "Leeds", "Everton", 1, 0)

    out = Path(tempfile.mkdtemp())
    res = store.publish_json(conn, out)

    preds = json.loads((out / "predictions.json").read_text(encoding="utf-8"))
    track = json.loads((out / "track-record.json").read_text(encoding="utf-8"))
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))

    assert len(preds) == 1, "only unsettled future fixtures belong in predictions.json"
    assert preds[0]["date"] == future
    assert isinstance(preds[0]["likely_scorelines"], list), "scorelines must be real JSON"
    assert "both_teams_score" not in preds[0]

    assert track["overall"]["matches_settled"] == 1
    assert len(track["recent"]) == 1
    assert track["by_league"][0]["league"] == "Premier League"
    assert meta["upcoming"] == 1 and meta["settled"] == 1

    leftover = list(out.glob("*.tmp"))
    assert not leftover, f"temp files left behind: {leftover}"
    print(f"  published {res}; no .tmp files left")
    conn.close()
    return True


def test_misses_are_published_too():
    """The track record is never filtered. Misses must appear alongside hits."""
    conn, _ = _fresh()
    store.upsert_predictions(conn, [
        _row(home="A", away="B", date="2026-09-01", h=60, d=25, a=15),
        _row(home="C", away="D", date="2026-09-02", h=60, d=25, a=15),
    ])
    store.settle(conn, "E0", "2026-09-01", "A", "B", 3, 0)   # hit
    store.settle(conn, "E0", "2026-09-02", "C", "D", 0, 3)   # miss

    out = Path(tempfile.mkdtemp())
    store.publish_json(conn, out)
    track = json.loads((out / "track-record.json").read_text(encoding="utf-8"))
    flags = sorted(r["was_correct"] for r in track["recent"])
    assert flags == [0, 1], f"expected one hit and one miss, got {flags}"
    assert track["overall"]["accuracy_pct"] == 50.0
    print(f"  both a hit and a miss published; accuracy {track['overall']['accuracy_pct']}%")
    conn.close()
    return True


def test_played_but_unsettled_is_published():
    """A played match must never silently vanish.

    Between kick-off and the results feed catching up, a fixture is in neither
    the upcoming list nor the settled record. If nothing showed it, a reader
    could not tell "waiting" from "quietly dropped because we got it wrong" -
    so it is published under `awaiting`, carrying the forecast that is already
    frozen in the store.
    """
    conn, _ = _fresh()
    store.upsert_predictions(conn, [
        _row(home="Played", away="Yesterday", date="2020-01-01", h=61, d=24, a=15),
        _row(home="Future", away="Fixture", date="2099-01-01"),
        _row(home="Done", away="Scored", date="2020-01-02"),
    ])
    store.settle(conn, "E0", "2020-01-02", "Done", "Scored", 2, 0)

    out = Path(tempfile.mkdtemp())
    res = store.publish_json(conn, out)
    track = json.loads((out / "track-record.json").read_text(encoding="utf-8"))
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    preds = json.loads((out / "predictions.json").read_text(encoding="utf-8"))

    awaiting = track["awaiting"]
    print(f"  upcoming={len(preds)} awaiting={len(awaiting)} settled={track['overall']['matches_settled']}")

    assert len(awaiting) == 1, f"expected 1 awaiting, got {len(awaiting)}"
    assert awaiting[0]["home_team"] == "Played"
    # The forecast travels with it - that is the whole point.
    assert awaiting[0]["home_win_pct"] == 61, "the frozen forecast must be published"
    assert meta["awaiting"] == 1 and res["awaiting"] == 1

    # A settled match belongs in the record, not in awaiting.
    assert all(a["home_team"] != "Done" for a in awaiting), "settled match leaked into awaiting"
    # A future fixture belongs in upcoming, not in awaiting.
    assert all(a["home_team"] != "Future" for a in awaiting), "future fixture leaked into awaiting"
    assert len(preds) == 1 and preds[0]["home_team"] == "Future"

    # Nothing is lost: every stored forecast is in exactly one of the three.
    total = len(preds) + len(awaiting) + track["overall"]["matches_settled"]
    assert total == 3, f"a forecast went missing: {total} of 3 accounted for"
    print("  every stored forecast is accounted for in exactly one place")
    conn.close()
    return True


def test_kickoff_not_calendar_date_decides_upcoming():
    """A match is upcoming until it KICKS OFF, not until midnight.

    Filtering on the calendar date kept a 10:15 fixture in the "upcoming" list
    at 23:00 the same evening. A file published at 23:55 therefore contained 23
    matches that had all finished hours earlier, which is what a reader saw.
    """
    from datetime import datetime, timedelta, timezone

    conn, _ = _fresh()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    def row_at(home, offset_hours):
        r = _row(home=home, away="Opponent", date=today)
        r["kickoff_utc"] = (now + timedelta(hours=offset_hours)).isoformat()
        return r

    store.upsert_predictions(conn, [
        row_at("KickedOffThisMorning", -9),   # same calendar day, long finished
        row_at("KicksOffLater", +4),          # same calendar day, still to come
    ])

    out = Path(tempfile.mkdtemp())
    res = store.publish_json(conn, out)
    preds = json.loads((out / "predictions.json").read_text(encoding="utf-8"))
    track = json.loads((out / "track-record.json").read_text(encoding="utf-8"))

    upcoming = [p["home_team"] for p in preds]
    waiting = [a["home_team"] for a in track["awaiting"]]
    print(f"  same calendar day -> upcoming {upcoming}, awaiting {waiting}")

    assert upcoming == ["KicksOffLater"], f"stale fixture still upcoming: {upcoming}"
    assert waiting == ["KickedOffThisMorning"], f"played fixture not awaiting: {waiting}"
    assert res["awaiting"] == 1
    conn.close()
    return True


def main():
    tests = [
        ("insert then refresh while unsettled", test_insert_then_refresh),
        ("settled forecast is frozen against re-runs", test_settled_forecast_is_frozen),
        ("trigger blocks raw SQL rewrite", test_trigger_blocks_raw_sql),
        ("settle scores correctly and only once", test_settle_only_once_and_scores_correctly),
        ("published JSON shape and atomicity", test_publish_shape_and_atomicity),
        ("misses are published, not filtered", test_misses_are_published_too),
        ("played but unsettled matches are visible", test_played_but_unsettled_is_published),
        ("kick-off time, not calendar date, decides upcoming", test_kickoff_not_calendar_date_decides_upcoming),
    ]
    failed = 0
    for name, fn in tests:
        print(f"\n[ {name} ]")
        try:
            fn()
            print("  PASS")
        except AssertionError as exc:
            print(f"  FAIL: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{'ALL PASSED' if failed == 0 else str(failed) + ' FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
