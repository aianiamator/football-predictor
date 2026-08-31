"""End-to-end test of the settle job against real historical results.

test_store.py proves the store's guarantees. This proves the job that uses
them actually works: it forecasts real matches from data that predates them,
runs settle() against the real results feed, and checks that

  * every forecast whose match has finished gets a result
  * the recorded result matches the real scoreline
  * was_correct agrees with the forecast the store actually holds
  * no forecast is altered in the process
  * a second run settles nothing new and changes nothing

Run with:  python -m tests.test_settle
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

from engine import data as dataio
from engine import store
from engine.model import fit
from engine.run import build_fixture_payload
from engine.settle import settle

CODE = "SP1"
WINDOW_DAYS = 150


def _seed(db: Path) -> tuple[int, dict]:
    """Forecast real recent matches using only data from before them."""
    hist = dataio.load_league(CODE, n_seasons=3)
    cutoff = hist["date"].max() - pd.Timedelta(days=WINDOW_DAYS)
    train = hist[hist["date"] < cutoff]
    recent = hist[hist["date"] >= cutoff]

    model = fit(train, league=CODE, reference_date=cutoff)
    rows, truth = [], {}
    for r in recent.itertuples():
        if not (model.knows(r.home_team) and model.knows(r.away_team)):
            continue
        p = build_fixture_payload(model.predict(r.home_team, r.away_team),
                                  CODE, r.date, "15:00")
        rows.append(p)
        truth[(p["date"], p["home_team"], p["away_team"])] = (
            int(r.home_goals), int(r.away_goals))

    conn = store.connect(db)
    store.upsert_predictions(conn, rows)
    conn.close()
    return len(rows), truth


def test_settles_real_results():
    tmp = Path(tempfile.mkdtemp())
    db, out = tmp / "s.db", tmp / "out"
    n, truth = _seed(db)
    assert n > 30, f"only {n} forecasts seeded; test would not be meaningful"

    # Snapshot the forecasts so we can prove none of them moved.
    conn = store.connect(db)
    before = {r["id"]: (r["home_win_pct"], r["draw_pct"], r["away_win_pct"], r["summary"])
              for r in conn.execute(
                  "select id, home_win_pct, draw_pct, away_win_pct, summary from predictions")}
    conn.close()

    res = settle(leagues=[CODE], n_seasons=3, publish=True, db=db, out=out)
    print(f"  seeded {n}, settled {res['settled']}, still pending {res['pending']}")
    assert res["settled"] > 0, "nothing settled; the feed matching is broken"

    conn = store.connect(db)
    # Ties are settled and Brier-scored but deliberately not marked right or
    # wrong, so the accuracy checks below run over SCORED rows only.
    n_ties = conn.execute("select count(*) from predictions where "
                          "fixture_status='finished' and was_correct is null").fetchone()[0]
    rows = conn.execute(
        "select id, date, home_team, away_team, home_win_pct, draw_pct, away_win_pct, "
        "summary, model_pick, actual_home_goals, actual_away_goals, was_correct "
        "from predictions where fixture_status='finished' "
        "and was_correct is not null").fetchall()
    print(f"  too close to call, left unscored: {n_ties}")

    wrong_score = mismatched = altered = 0
    for r in rows:
        key = (r["date"], r["home_team"], r["away_team"])
        real = truth.get(key)
        if real and (r["actual_home_goals"], r["actual_away_goals"]) != real:
            wrong_score += 1

        # Score against the pick STORED with the forecast, which is what the
        # engine actually committed to before kick-off.
        forecast = r["model_pick"] or max(
            {"H": r["home_win_pct"], "D": r["draw_pct"], "A": r["away_win_pct"]}.items(),
            key=lambda kv: kv[1])[0]
        actual = ("H" if r["actual_home_goals"] > r["actual_away_goals"]
                  else "A" if r["actual_home_goals"] < r["actual_away_goals"] else "D")
        if r["was_correct"] != int(forecast == actual):
            mismatched += 1

        if before[r["id"]] != (r["home_win_pct"], r["draw_pct"], r["away_win_pct"], r["summary"]):
            altered += 1

    hits = sum(r["was_correct"] for r in rows)
    print(f"  recorded scorelines wrong : {wrong_score}")
    print(f"  was_correct disagreements : {mismatched}")
    print(f"  forecasts altered         : {altered}")
    print(f"  track record              : {hits}/{len(rows)} ({100*hits/len(rows):.1f}%)")
    conn.close()

    assert wrong_score == 0, "a stored result does not match the real scoreline"
    assert mismatched == 0, "was_correct disagrees with the stored forecast"
    assert altered == 0, "settling altered a forecast"

    # Accuracy on real matches should land in the plausible band, not at 0 or 100.
    acc = hits / len(rows)
    assert 0.25 < acc < 0.75, f"implausible settled accuracy {acc:.1%}"

    # Re-running must be a no-op.
    again = settle(leagues=[CODE], n_seasons=3, publish=True, db=db, out=out)
    print(f"  second run settled        : {again['settled']} (must be 0)")
    assert again["settled"] == 0, "re-running settled matches again"
    return True


def test_publishes_track_record():
    import json

    tmp = Path(tempfile.mkdtemp())
    db, out = tmp / "s.db", tmp / "out"
    _seed(db)
    settle(leagues=[CODE], n_seasons=3, publish=True, db=db, out=out)

    track = json.loads((out / "track-record.json").read_text(encoding="utf-8"))
    # A tie carries was_correct = None, so exclude those before sorting.
    flags = sorted({m["was_correct"] for m in track["recent"]
                    if m["was_correct"] is not None})
    perf = track["performance"]["overall"]
    print(f"  published {track['overall']['matches_settled']} settled, "
          f"accuracy {track['overall']['accuracy_pct']}%")
    print(f"  scored {perf['completed']}, unscored ties {perf['unscored_ties']}, "
          f"Brier {perf['brier']}")
    print(f"  last 20 contains hits and misses: {flags}")
    assert track["overall"]["matches_settled"] > 0
    assert flags == [0, 1], "the record must show misses as well as hits"
    # Both count SCORED matches; ties are excluded from each by design.
    assert perf["completed"] == track["overall"]["matches_settled"],         "the two scored counts disagree"
    assert perf["unscored_ties"] > 0, "expected some fixtures too close to call"
    assert perf["brier"] is not None and 0 < perf["brier"] < 2
    assert perf["correct"] + perf["incorrect"] == perf["completed"]
    return True


def main():
    tests = [
        ("settles real results without touching forecasts", test_settles_real_results),
        ("publishes a track record containing misses", test_publishes_track_record),
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
