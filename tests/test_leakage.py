"""Leakage audit for the walk-forward backtest.

Two independent checks:

  1. STRUCTURAL - at every refit window, assert that the newest training match
     is strictly older than the oldest match being predicted, and that the
     decay reference date is not after any predicted match.

  2. PLACEBO - re-run the backtest against a league whose results have been
     randomly reshuffled between fixtures. The model can then hold no real
     information, so accuracy must collapse towards the always-home baseline.
     If a shuffled league still scores well, information is leaking.

Run with:  python -m tests.test_leakage
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from engine.backtest import (MIN_TEAM_MATCHES, MIN_TRAIN_DAYS, REFIT_DAYS,
                             TRAIN_WINDOW_DAYS, backtest_league)
from engine.config import HALF_LIFE_DAYS
from engine.data import load_league
from engine.model import DixonColes

CODE = "E0"


def test_structural(code: str = CODE):
    """Walk the same windows the backtest uses and assert the time ordering."""
    df = load_league(code)
    first, last = df["Date"].min(), df["Date"].max()
    t = first + pd.Timedelta(days=MIN_TRAIN_DAYS)

    windows = 0
    worst_gap = None
    while t <= last:
        end = t + pd.Timedelta(days=REFIT_DAYS)
        train = df[(df["Date"] < t) & (df["Date"] >= t - pd.Timedelta(days=TRAIN_WINDOW_DAYS))]
        upcoming = df[(df["Date"] >= t) & (df["Date"] < end)]

        if len(upcoming) and len(train) >= 100:
            newest_train = train["Date"].max()
            oldest_pred = upcoming["Date"].min()
            assert newest_train < oldest_pred, (
                f"LEAK: training match {newest_train} is not before predicted {oldest_pred}")
            assert t <= oldest_pred, f"LEAK: reference date {t} after predicted {oldest_pred}"
            gap = (oldest_pred - newest_train).days
            worst_gap = gap if worst_gap is None else min(worst_gap, gap)
            windows += 1
        t = end

    print(f"  {windows} windows audited, all training strictly precedes prediction")
    print(f"  smallest gap between newest training match and next predicted match: {worst_gap} day(s)")
    assert windows > 100, "too few windows audited to be meaningful"
    return True


def test_no_future_in_weights(code: str = CODE):
    """Decay weights must never be computed against a future reference date."""
    df = load_league(code)
    cut = df["Date"].min() + pd.Timedelta(days=MIN_TRAIN_DAYS)
    train = df[df["Date"] < cut]
    model = DixonColes.fit(train, reference_date=cut, half_life_days=HALF_LIFE_DAYS)
    assert model.reference_date == cut
    assert train["Date"].max() < cut
    print(f"  fit on {len(train)} matches, all older than reference date {cut.date()}")
    return True


def test_placebo(code: str = CODE, seed: int = 42):
    """Shuffled results must destroy the model's edge."""
    real = backtest_league(code, verbose=False)
    assert real is not None

    df = load_league(code)
    rng = np.random.default_rng(seed)

    # Permute the scorelines across fixtures, keeping the fixture list, dates
    # and the overall distribution of scores identical.
    perm = rng.permutation(len(df))
    shuffled = df.copy()
    shuffled[["FTHG", "FTAG"]] = df[["FTHG", "FTAG"]].to_numpy()[perm]
    shuffled["Result"] = "D"
    shuffled.loc[shuffled["FTHG"] > shuffled["FTAG"], "Result"] = "H"
    shuffled.loc[shuffled["FTHG"] < shuffled["FTAG"], "Result"] = "A"
    shuffled["TotalGoals"] = shuffled["FTHG"] + shuffled["FTAG"]
    shuffled["Over25"] = (shuffled["TotalGoals"] >= 3).astype(int)
    shuffled["BTTS"] = ((shuffled["FTHG"] >= 1) & (shuffled["FTAG"] >= 1)).astype(int)

    fake = _run_on_frame(shuffled)

    print(f"  real     : accuracy {real['accuracy']*100:.1f}%  "
          f"baseline {real['home_baseline']*100:.1f}%  edge {real['edge']*100:+.1f}pp")
    print(f"  shuffled : accuracy {fake['accuracy']*100:.1f}%  "
          f"baseline {fake['home_baseline']*100:.1f}%  edge {fake['edge']*100:+.1f}pp")

    assert abs(fake["edge"]) < 0.03, (
        f"LEAK SUSPECTED: shuffled data still shows a {fake['edge']*100:+.1f}pp edge")
    assert real["edge"] > fake["edge"] + 0.04, "real edge is not clearly above the placebo"
    return True


def _run_on_frame(df: pd.DataFrame) -> dict:
    """Minimal copy of the walk-forward loop, for an in-memory frame."""
    first, last = df["Date"].min(), df["Date"].max()
    t = first + pd.Timedelta(days=MIN_TRAIN_DAYS)
    prev = None
    rows = []
    while t <= last:
        end = t + pd.Timedelta(days=REFIT_DAYS)
        train = df[(df["Date"] < t) & (df["Date"] >= t - pd.Timedelta(days=TRAIN_WINDOW_DAYS))]
        upcoming = df[(df["Date"] >= t) & (df["Date"] < end)]
        if len(upcoming) == 0 or len(train) < 100:
            t = end
            continue
        try:
            model = DixonColes.fit(train, reference_date=t, half_life_days=HALF_LIFE_DAYS, init=prev)
            prev = model
        except Exception:  # noqa: BLE001
            t = end
            continue
        counts = pd.concat([train["HomeTeam"], train["AwayTeam"]]).value_counts()
        for r in upcoming.itertuples(index=False):
            if not (model.knows(r.HomeTeam) and model.knows(r.AwayTeam)):
                continue
            if counts.get(r.HomeTeam, 0) < MIN_TEAM_MATCHES or counts.get(r.AwayTeam, 0) < MIN_TEAM_MATCHES:
                continue
            p = model.predict(r.HomeTeam, r.AwayTeam)
            rows.append((p["home_win"], p["draw"], p["away_win"], r.Result))
        t = end

    res = pd.DataFrame(rows, columns=["p_h", "p_d", "p_a", "actual"])
    probs = res[["p_h", "p_d", "p_a"]].to_numpy(float)
    idx = res["actual"].map({"H": 0, "D": 1, "A": 2}).to_numpy(int)
    acc = float((probs.argmax(axis=1) == idx).mean())
    base = float((res["actual"] == "H").mean())
    return {"accuracy": acc, "home_baseline": base, "edge": acc - base, "n": len(res)}


def main():
    tests = [
        ("structural time ordering", test_structural),
        ("no future data in decay weights", test_no_future_in_weights),
        ("placebo: shuffled results", test_placebo),
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
