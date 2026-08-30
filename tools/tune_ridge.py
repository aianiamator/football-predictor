"""Select the ridge penalty by chronological out-of-sample validation.

Leakage discipline
------------------
The walk-forward backtest is already leakage-free per match: a forecast only
ever sees matches played before it. But CHOOSING a hyper-parameter introduces a
second, subtler leak - if you pick the value that scores best on the same
matches you then report, you have fitted the test set through the back door.

So the out-of-sample predictions are split by DATE:

    validation period   ->  selects ridge.  Reported here.
    test period         ->  never consulted while choosing. Reported by
                            tools/compare_models.py once ridge is fixed.

The split date is set once, before any value is examined.

Run:  python -m tools.tune_ridge
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from engine import data as dataio
from engine.backtest import backtest_league
from engine.evaluate import brier, log_loss, wilson_interval

# Fixed before looking at any result.
SPLIT = pd.Timestamp("2024-01-01")
RIDGE_GRID = [0.0, 0.25, 0.5, 1.0, 2.0, 5.0]


def run(ridge: float, matches: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for code in dataio.CORE_LEAGUES:
        r = backtest_league(matches, code, ridge=ridge)
        if len(r):
            frames.append(r)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def score(df: pd.DataFrame) -> dict:
    P = df[["p_home", "p_draw", "p_away"]].to_numpy(float)
    y = df["actual"].map({"H": 0, "D": 1, "A": 2}).to_numpy(int)
    pred = P.argmax(1)
    hits = int((pred == y).sum())
    return {
        "n": len(df),
        "log_loss": log_loss(P, y),
        "brier": brier(P, y),
        "accuracy": hits / len(df),
        "implausible": int((P[:, 1] > 0.45).sum()),
        "max_draw_prob": float(P[:, 1].max()),
    }


def main() -> int:
    print("Loading history...")
    matches = dataio.load_many(dataio.CORE_LEAGUES, n_seasons=8)

    print(f"\nSelecting ridge on matches BEFORE {SPLIT.date()} only.")
    print("The later period is not consulted here.\n")
    print(f"  {'ridge':>7}{'n':>8}{'log loss':>11}{'Brier':>10}{'accuracy':>11}"
          f"{'P(draw)>.45':>13}{'max P(draw)':>13}")

    results = {}
    for r in RIDGE_GRID:
        out = run(r, matches)
        if out.empty:
            continue
        out["date"] = pd.to_datetime(out["date"])
        val = out[out["date"] < SPLIT]
        s = score(val)
        results[r] = (s, out)
        print(f"  {r:>7.2f}{s['n']:>8,}{s['log_loss']:>11.5f}{s['brier']:>10.5f}"
              f"{s['accuracy']*100:>10.2f}%{s['implausible']:>13}{s['max_draw_prob']:>13.3f}")

    if not results:
        print("No results.")
        return 1

    # Log loss is the selection criterion: it is a strictly proper scoring rule
    # and it punishes exactly the failure being fixed - confident nonsense.
    best = min(results, key=lambda r: results[r][0]["log_loss"])
    base = results[RIDGE_GRID[0]][0]
    print(f"\n  Selected ridge = {best} on validation log loss "
          f"({results[best][0]['log_loss']:.5f} vs {base['log_loss']:.5f} unpenalised)")
    print(f"  Set RIDGE = {best} in engine/config.py, then run tools/compare_models.py")
    print(f"  to measure the held-out period from {SPLIT.date()} onward.")

    for r, (s, out) in results.items():
        out.to_csv(f"backtest_ridge_{r}.csv", index=False)
    print(f"\n  Per-match predictions written for each ridge value.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
