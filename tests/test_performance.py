"""Settlement statuses, scoring and the performance analytics.

Covers the cases that decide whether the public hit rate is honest:

  * a postponed or abandoned match must not count as right OR wrong
  * a tie (no separable favourite) must not be scored either way
  * Brier is computed per match and averaged only over scored matches
  * confidence, outcome, league and calibration blocks agree with the rows
  * every rate carries its sample size

Run with:  python -m tests.test_performance
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from engine import store
from engine.performance import performance, sample_band
from engine.run import decide


def _row(home, away, h, d, a, date="2020-01-01"):
    dec = decide(h, d, a)
    return {
        "league_code": "E0", "league": "Premier League", "country": "England",
        "date": date, "kickoff": "15:00", "kickoff_utc": f"{date}T15:00:00+00:00",
        "home_team": home, "away_team": away,
        "home_win_pct": h, "draw_pct": d, "away_win_pct": a,
        "over_2_5_pct": None, "clean_sheet_home_pct": 40, "clean_sheet_away_pct": 20,
        "expected_goals_home": 1.8, "expected_goals_away": 0.9,
        "likely_score": "2-0", "likely_scorelines": [],
        "confidence": "moderate", "confidence_stars": 2, "confidence_colour": "#b45309",
        "summary": "x", "summary_key": "more_likely", "summary_args": {},
        "model_version": "1.1.0", "generated_at": "2026-01-01T00:00:00+00:00",
        **dec,
    }


def _fresh():
    return store.connect(Path(tempfile.mkdtemp()) / "t.db")


def test_not_played_never_counts():
    """Postponed and abandoned matches leave the queue without being scored."""
    conn = _fresh()
    store.upsert_predictions(conn, [
        _row("A", "B", 70, 18, 12),
        _row("C", "D", 65, 20, 15, date="2020-01-02"),
        _row("E", "F", 60, 22, 18, date="2020-01-03"),
    ])
    store.settle(conn, "E0", "2020-01-01", "A", "B", 2, 0)          # correct
    assert store.mark_not_played(conn, "E0", "2020-01-02", "C", "D", "postponed")
    assert store.mark_not_played(conn, "E0", "2020-01-03", "E", "F", "abandoned")

    perf = performance(conn)["overall"]
    print(f"  completed={perf['completed']} correct={perf['correct']} "
          f"not_played={perf['not_played']} pending={perf['pending']} "
          f"hit_rate={perf['hit_rate']}")

    assert perf["completed"] == 1, "a not-played match leaked into the scored set"
    assert perf["correct"] == 1
    assert perf["hit_rate"] == 100.0
    assert perf["not_played"] == 2
    assert perf["pending"] == 0, "not-played matches must leave the pending queue"

    # And they must not appear as "awaiting a result" either.
    out = Path(tempfile.mkdtemp())
    store.publish_json(conn, out)
    track = json.loads((out / "track-record.json").read_text(encoding="utf-8"))
    assert track["awaiting_total"] == 0, "a postponed match is still shown as waiting"
    conn.close()
    return True


def test_tie_is_recorded_but_not_scored():
    """A fixture with no separable favourite must not move the hit rate."""
    conn = _fresh()
    store.upsert_predictions(conn, [_row("A", "B", 37, 26, 37)])
    row = conn.execute("select model_pick, confidence_margin from predictions").fetchone()
    assert row["model_pick"] == "TIE", f"expected TIE, got {row['model_pick']}"

    store.settle(conn, "E0", "2020-01-01", "A", "B", 3, 0)
    got = conn.execute("select fixture_status, actual_result, was_correct, brier_score "
                       "from predictions").fetchone()
    print(f"  status={got['fixture_status']} result={got['actual_result']} "
          f"was_correct={got['was_correct']} brier={got['brier_score']:.4f}")

    assert got["fixture_status"] == "finished"
    assert got["actual_result"] == "HOME"
    assert got["was_correct"] is None, "a tie must not be scored right or wrong"
    assert got["brier_score"] is not None, "a tie should still be Brier-scored"

    perf = performance(conn)["overall"]
    assert perf["completed"] == 0, "tie leaked into the hit rate"
    assert perf["unscored_ties"] == 1
    conn.close()
    return True


def test_brier_matches_the_definition():
    """Per-match Brier must equal the textbook sum of squared errors."""
    conn = _fresh()
    store.upsert_predictions(conn, [_row("A", "B", 70, 18, 12)])
    store.settle(conn, "E0", "2020-01-01", "A", "B", 1, 0)   # HOME
    got = conn.execute("select brier_score from predictions").fetchone()["brier_score"]
    expected = (0.70 - 1) ** 2 + (0.18 - 0) ** 2 + (0.12 - 0) ** 2
    print(f"  stored {got:.6f}  expected {expected:.6f}")
    assert abs(got - expected) < 1e-9, f"{got} != {expected}"
    conn.close()
    return True


def test_blocks_agree_with_rows():
    """Confidence, outcome and league blocks must reconcile with the raw data."""
    conn = _fresh()
    rows, truth = [], []
    # Deterministic mix: high-confidence right, moderate wrong, away pick right.
    specs = [("A", "B", 75, 15, 10, 2, 0), ("C", "D", 55, 25, 20, 0, 2),
             ("E", "F", 20, 25, 55, 0, 3), ("G", "H", 72, 16, 12, 1, 1)]
    for i, (h, a, ph, pd_, pa, hg, ag) in enumerate(specs):
        d = f"2020-02-{i+1:02d}"
        rows.append(_row(h, a, ph, pd_, pa, date=d))
        truth.append((d, h, a, hg, ag))
    store.upsert_predictions(conn, rows)
    for d, h, a, hg, ag in truth:
        store.settle(conn, "E0", d, h, a, hg, ag)

    perf = performance(conn)
    o = perf["overall"]
    conf_total = sum(b["completed"] for b in perf["by_confidence"])
    out_total = sum(b["completed"] for b in perf["by_outcome"])
    lg_total = sum(b["completed"] for b in perf["by_league"])
    cal_total = sum(b["predictions"] for b in perf["calibration"])

    print(f"  overall={o['completed']} confidence={conf_total} outcome={out_total} "
          f"league={lg_total} calibration={cal_total}")
    print(f"  hit_rate={o['hit_rate']}%  brier={o['brier']}  sample={o['sample_band']}")
    print(f"  baseline always-home={perf['baselines']['always_home']['hit_rate']}%")

    assert conf_total == o["completed"], "confidence blocks do not reconcile"
    assert out_total == o["completed"], "outcome blocks do not reconcile"
    assert lg_total == o["completed"], "league blocks do not reconcile"
    assert cal_total == o["completed"], "calibration blocks do not reconcile"
    assert o["correct"] + o["incorrect"] == o["completed"]
    assert perf["model_versions"].get("1.1.0") == 4, "model version not stamped"
    conn.close()
    return True


def test_sample_bands():
    cases = [(0, "very_small"), (29, "very_small"), (30, "early"), (99, "early"),
             (100, "developing"), (499, "developing"), (500, "larger_sample")]
    for n, expected in cases:
        assert sample_band(n) == expected, f"{n} -> {sample_band(n)}, want {expected}"
    print(f"  {len(cases)} thresholds correct")
    return True


def main():
    tests = [
        ("postponed/abandoned never counted", test_not_played_never_counts),
        ("ties recorded but not scored", test_tie_is_recorded_but_not_scored),
        ("Brier matches the definition", test_brier_matches_the_definition),
        ("analytics blocks reconcile with rows", test_blocks_agree_with_rows),
        ("sample size bands", test_sample_bands),
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
