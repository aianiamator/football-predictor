"""Compare the unpenalised and regularised engines on HELD-OUT matches.

The ridge value was selected in tools/tune_ridge.py using only matches before
SPLIT. This script reports the period from SPLIT onward, which was not
consulted during selection. Both models are scored on the identical set of
matches, so the paired tests remove match difficulty as a source of variance.

Baselines are included because "better than before" is not the same as "good".

Run:  python -m tools.compare_models
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from engine.evaluate import (evaluate, paired_score_test, per_match_brier,
                             per_match_log_loss, print_report, reliability,
                             wilson_interval)

SPLIT = pd.Timestamp("2024-01-01")
IDX = {"H": 0, "D": 1, "A": 2}


def load(ridge: float) -> pd.DataFrame:
    df = pd.read_csv(f"backtest_ridge_{ridge}.csv")
    df["date"] = pd.to_datetime(df["date"])
    return df[df["date"] >= SPLIT].reset_index(drop=True)


def probs(df):
    return df[["p_home", "p_draw", "p_away"]].to_numpy(float)


def outcomes(df):
    return df["actual"].map(IDX).to_numpy(int)


def main() -> int:
    old, new = load(0.0), load(2.0)
    # Align to the identical match set so the comparison is genuinely paired.
    key = ["league", "date", "home_team", "away_team"]
    merged = old.merge(new, on=key, suffixes=("_old", "_new"))
    n = len(merged)
    y = merged["actual_old"].map(IDX).to_numpy(int)
    Pold = merged[["p_home_old", "p_draw_old", "p_away_old"]].to_numpy(float)
    Pnew = merged[["p_home_new", "p_draw_new", "p_away_new"]].to_numpy(float)

    print(f"HELD-OUT TEST PERIOD: {merged['date'].min().date()} to {merged['date'].max().date()}")
    print(f"{n:,} matches, identical set for both models.")
    print("Ridge was selected on EARLIER matches only and is fixed here.")

    print_report(evaluate(Pold, y, "BEFORE - unpenalised (ridge = 0)"))
    print_report(evaluate(Pnew, y, "AFTER - regularised (ridge = 2.0)"))

    # ---- baselines, same matches -------------------------------------
    uniform = np.tile([1 / 3, 1 / 3, 1 / 3], (n, 1))
    rates = np.bincount(y, minlength=3) / n
    climatology = np.tile(rates, (n, 1))
    print_report(evaluate(uniform, y, "BASELINE - uniform 1/3 each"))
    print_report(evaluate(climatology, y, "BASELINE - league base rates"))

    have_odds = merged["odds_home_old"].notna()
    if have_odds.sum() > 100:
        o = merged.loc[have_odds, ["odds_home_old", "odds_draw_old", "odds_away_old"]].to_numpy(float)
        imp = (1 / o)
        imp = imp / imp.sum(1, keepdims=True)
        print_report(evaluate(imp, y[have_odds.to_numpy()], "BENCHMARK - market, overround removed"))

    # ---- is the change statistically convincing? ----------------------
    print("\n" + "=" * 70)
    print("IS THE IMPROVEMENT REAL? (paired, same matches)")
    print("=" * 70)
    for name, fn in [("log loss", per_match_log_loss), ("Brier", per_match_brier)]:
        t = paired_score_test(fn(Pold, y), fn(Pnew, y))
        lo, hi = t["ci95"]
        verdict = ("CONVINCING" if t["p_value"] < 0.01 else
                   "suggestive" if t["p_value"] < 0.05 else "NOT significant")
        print(f"  {name:<10} mean improvement {t['mean_diff']:+.5f} "
              f"95% CI [{lo:+.5f}, {hi:+.5f}]  p = {t['p_value']:.2e}  -> {verdict}")

    a_old = int((Pold.argmax(1) == y).sum())
    a_new = int((Pnew.argmax(1) == y).sum())
    lo_o, hi_o = wilson_interval(a_old, n)
    lo_n, hi_n = wilson_interval(a_new, n)
    print(f"\n  accuracy   before {a_old/n*100:.2f}% [{lo_o*100:.2f}, {hi_o*100:.2f}]"
          f"   after {a_new/n*100:.2f}% [{lo_n*100:.2f}, {hi_n*100:.2f}]")
    print("  The accuracy intervals overlap heavily; accuracy is NOT where the")
    print("  improvement lives, and claiming it would be overselling.")

    # ---- what actually changed ---------------------------------------
    print("\n" + "=" * 70)
    print("WHAT THE PENALTY ACTUALLY FIXED")
    print("=" * 70)
    bad_old = int((Pold[:, 1] > 0.45).sum())
    bad_new = int((Pnew[:, 1] > 0.45).sum())
    print(f"  forecasts claiming P(draw) > 45%   before {bad_old}   after {bad_new}")
    print(f"  highest P(draw) published          before {Pold[:,1].max():.3f}   after {Pnew[:,1].max():.3f}")
    worst_old = per_match_log_loss(Pold, y)
    worst_new = per_match_log_loss(Pnew, y)
    print(f"  worst single-match log loss        before {worst_old.max():.2f}   after {worst_new.max():.2f}")
    print(f"  matches scoring worse than 3.0     before {(worst_old>3).sum()}   after {(worst_new>3).sum()}")
    print("\n  The gain comes from removing confident nonsense, not from being")
    print("  cleverer about ordinary matches. That is what regularisation does.")

    print("\n" + "=" * 70)
    print("CALIBRATION, AFTER (pooled H/D/A)")
    print("=" * 70)
    print(f"  {'band':<12}{'n':>8}{'predicted':>12}{'observed':>11}{'gap':>9}")
    for r in reliability(Pnew, y):
        if r["n"]:
            print(f"  {r['bin']:<12}{r['n']:>8,}{r['mean_predicted']*100:>11.2f}%"
                  f"{r['observed']*100:>10.2f}%{r['gap']*100:>+8.2f}pp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
