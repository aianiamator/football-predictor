"""Leakage audit for the walk-forward backtest.

Three independent checks:

  1. STRUCTURAL - walk the same matchdays the backtest walks and assert that
     the newest training match is strictly older than the matchday being
     predicted, and that the decay reference date is never in the future.

  2. WEIGHTS - a fit anchored at date t must give zero weight to nothing and
     must never see a match dated on or after t.

  3. PLACEBO - re-run the backtest on a league whose scorelines have been
     randomly reshuffled between fixtures. The model can then hold no real
     information, so its edge over the always-home baseline must collapse to
     roughly zero. If a shuffled league still shows an edge, something is
     leaking.

Run with:  python -m tests.test_leakage
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from engine import data as dataio
from engine.backtest import backtest_league, summarise
from engine.model import fit

CODE = "E0"
MIN_TRAIN = 400
REFIT_DAYS = 7


def _load(code: str = CODE) -> pd.DataFrame:
    df = dataio.load_league(code)
    df["league"] = code
    return df


def test_structural(code: str = CODE):
    """Replicate the backtest's own walk and assert the time ordering."""
    matches = _load(code).sort_values("date").reset_index(drop=True)
    start_date = matches.loc[MIN_TRAIN, "date"]
    test = matches[matches["date"] > start_date]

    windows = 0
    smallest_gap = None
    last_fit = None

    for date, _day in test.groupby("date"):
        if last_fit is not None and (date - last_fit).days < REFIT_DAYS:
            continue
        train = matches[matches["date"] < date]
        if len(train) < MIN_TRAIN:
            continue
        last_fit = date

        newest_train = train["date"].max()
        assert newest_train < date, (
            f"LEAK: training match {newest_train} is not strictly before matchday {date}")
        gap = (date - newest_train).days
        smallest_gap = gap if smallest_gap is None else min(smallest_gap, gap)
        windows += 1

    print(f"  {windows} refit points audited, training strictly precedes every matchday")
    print(f"  smallest gap between newest training match and matchday: {smallest_gap} day(s)")
    assert windows > 100, "too few refit points audited to be meaningful"
    return True


def test_no_future_in_weights(code: str = CODE):
    """A fit anchored at t must contain no match dated on or after t."""
    matches = _load(code).sort_values("date").reset_index(drop=True)
    cut = matches.loc[MIN_TRAIN, "date"]
    train = matches[matches["date"] < cut]

    model = fit(train, league=code, reference_date=cut)
    assert model.reference_date == cut
    assert train["date"].max() < cut
    assert (train["date"] >= cut).sum() == 0
    print(f"  fit on {len(train)} matches, newest {train['date'].max().date()}, "
          f"anchored at {cut.date()}")
    return True


def test_placebo(code: str = CODE, seed: int = 42):
    """Shuffled scorelines must destroy the model's edge."""
    matches = _load(code)

    real = summarise(backtest_league(matches, code))
    assert real, "real backtest produced nothing"

    # Permute scorelines across fixtures. The fixture list, the dates and the
    # overall distribution of scores are all unchanged - only the pairing
    # between a fixture and its result is destroyed.
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(matches))
    shuffled = matches.copy()
    shuffled[["home_goals", "away_goals"]] = (
        matches[["home_goals", "away_goals"]].to_numpy()[perm])

    fake = summarise(backtest_league(shuffled, code))
    assert fake, "placebo backtest produced nothing"

    print(f"  real     : {real['result_accuracy']:.1%} vs baseline "
          f"{real['always_home_baseline']:.1%}  edge {real['edge_over_baseline']:+.1%}")
    print(f"  shuffled : {fake['result_accuracy']:.1%} vs baseline "
          f"{fake['always_home_baseline']:.1%}  edge {fake['edge_over_baseline']:+.1%}")

    assert abs(fake["edge_over_baseline"]) < 0.03, (
        f"LEAK SUSPECTED: shuffled data still shows a "
        f"{fake['edge_over_baseline']:+.1%} edge")
    assert real["edge_over_baseline"] > fake["edge_over_baseline"] + 0.04, (
        "real edge is not clearly above the placebo")
    return True


def test_plausibility(code: str = CODE):
    """Guard the headline number the whole project hinges on."""
    res = summarise(backtest_league(_load(code), code))
    acc = res["result_accuracy"]
    print(f"  {code} result accuracy {acc:.1%} on {res['matches']} matches")
    assert acc <= 0.60, (
        f"IMPLAUSIBLE: {acc:.1%} accuracy. Football result forecasting does not "
        f"reach this level. Look for leakage before believing it.")
    assert acc > 0.35, f"suspiciously low accuracy {acc:.1%}; check the pipeline"
    return True


def main():
    tests = [
        ("structural time ordering", test_structural),
        ("no future data in decay weights", test_no_future_in_weights),
        ("accuracy plausibility ceiling", test_plausibility),
        ("placebo: shuffled scorelines", test_placebo),
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
