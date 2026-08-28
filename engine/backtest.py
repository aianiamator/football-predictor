"""Walk-forward backtest with calibration analysis and a bookmaker benchmark.

Leakage discipline
------------------
The model is refitted every `REFIT_DAYS` days. At a refit point t:

  * training data is strictly `Date < t`
  * the time-decay reference date is t itself, so no future match can influence
    a weight
  * predictions are made only for matches in `t <= Date < t + REFIT_DAYS`
  * a fixture is skipped unless BOTH teams already appear in the training slice
    at least MIN_TEAM_MATCHES times

Nothing about a match - not its result, not its odds - is visible to the fit
that predicts it. If a league scores far above the ~50-55% band that result
forecasting realistically allows, suspect this discipline first.

Run with:  python -m engine.backtest
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ACTIVE, BY_CODE, HALF_LIFE_DAYS
from .data import implied_probabilities, load_league
from .model import DixonColes

REFIT_DAYS = 7            # refit cadence: one football week
MIN_TRAIN_DAYS = 730      # two seasons of history before the first prediction
TRAIN_WINDOW_DAYS = 1460  # cap training at 4 years; decay makes older data ~6% weight
MIN_TEAM_MATCHES = 6      # a team needs this much history to be predictable

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "backtest_results.json"

OUTCOMES = ["H", "D", "A"]
EPS = 1e-15


def _log_loss(probs: np.ndarray, actual_idx: np.ndarray) -> float:
    """Multiclass log loss over H/D/A."""
    if len(actual_idx) == 0:
        return float("nan")
    p = np.clip(probs[np.arange(len(actual_idx)), actual_idx], EPS, 1.0)
    return float(-np.mean(np.log(p)))


def backtest_league(code: str, verbose: bool = True) -> dict | None:
    """Walk forward through one league's history."""
    league = BY_CODE[code]
    df = load_league(code)
    if len(df) < 400:
        if verbose:
            print(f"  {code}: only {len(df)} matches, skipping")
        return None

    first_date = df["Date"].min()
    last_date = df["Date"].max()
    start = first_date + pd.Timedelta(days=MIN_TRAIN_DAYS)

    records = []
    skipped = 0
    n_fits = 0
    failed_fits = 0
    prev_model: DixonColes | None = None

    t = start
    t0 = time.time()
    while t <= last_date:
        window_end = t + pd.Timedelta(days=REFIT_DAYS)

        # --- training slice: strictly before t ---------------------------
        train = df[(df["Date"] < t) & (df["Date"] >= t - pd.Timedelta(days=TRAIN_WINDOW_DAYS))]
        upcoming = df[(df["Date"] >= t) & (df["Date"] < window_end)]

        if len(upcoming) == 0 or len(train) < 100:
            t = window_end
            continue

        try:
            model = DixonColes.fit(train, reference_date=t, half_life_days=HALF_LIFE_DAYS,
                                   init=prev_model)
            prev_model = model
            n_fits += 1
        except Exception:  # noqa: BLE001 - a failed fit must not kill the run
            failed_fits += 1
            t = window_end
            continue

        counts = pd.concat([train["HomeTeam"], train["AwayTeam"]]).value_counts()

        for row in upcoming.itertuples(index=False):
            if not (model.knows(row.HomeTeam) and model.knows(row.AwayTeam)):
                skipped += 1
                continue
            if counts.get(row.HomeTeam, 0) < MIN_TEAM_MATCHES or counts.get(row.AwayTeam, 0) < MIN_TEAM_MATCHES:
                skipped += 1
                continue

            pred = model.predict(row.HomeTeam, row.AwayTeam)
            bh, bd, ba = implied_probabilities(row.OddsH, row.OddsD, row.OddsA)

            records.append({
                "date": row.Date,
                "home": row.HomeTeam,
                "away": row.AwayTeam,
                "p_h": pred["home_win"], "p_d": pred["draw"], "p_a": pred["away_win"],
                "p_over": pred["over25"], "p_btts": pred["btts"],
                "actual": row.Result,
                "over": int(row.Over25), "btts": int(row.BTTS),
                "book_h": bh, "book_d": bd, "book_a": ba,
            })

        t = window_end

    if not records:
        return None

    res = pd.DataFrame(records)
    elapsed = time.time() - t0

    probs = res[["p_h", "p_d", "p_a"]].to_numpy(float)
    actual_idx = res["actual"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy(int)
    predicted_idx = probs.argmax(axis=1)

    accuracy = float((predicted_idx == actual_idx).mean())
    home_baseline = float((res["actual"] == "H").mean())
    draw_rate = float((res["actual"] == "D").mean())

    over_pred = (res["p_over"] >= 0.5).astype(int)
    over_acc = float((over_pred == res["over"]).mean())
    btts_pred = (res["p_btts"] >= 0.5).astype(int)
    btts_acc = float((btts_pred == res["btts"]).mean())

    logloss = _log_loss(probs, actual_idx)

    # --- bookmaker benchmark on the identical subset ---------------------
    has_odds = res["book_h"].notna()
    n_odds = int(has_odds.sum())
    if n_odds >= 50:
        sub = res[has_odds]
        sub_probs = sub[["p_h", "p_d", "p_a"]].to_numpy(float)
        sub_actual = sub["actual"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy(int)
        book_probs = sub[["book_h", "book_d", "book_a"]].to_numpy(float)

        model_acc_sub = float((sub_probs.argmax(axis=1) == sub_actual).mean())
        book_acc = float((book_probs.argmax(axis=1) == sub_actual).mean())
        model_ll_sub = _log_loss(sub_probs, sub_actual)
        book_ll = _log_loss(book_probs, sub_actual)
    else:
        model_acc_sub = book_acc = model_ll_sub = book_ll = float("nan")

    if verbose:
        print(f"  {code}: {len(res)} predictions, {n_fits} fits, {skipped} skipped, {elapsed:.0f}s")

    return {
        "code": code,
        "league": league.name,
        "country": league.country,
        "n_predictions": len(res),
        "n_fits": n_fits,
        "failed_fits": failed_fits,
        "skipped": skipped,
        "first_prediction": str(res["date"].min().date()),
        "last_prediction": str(res["date"].max().date()),
        "accuracy": accuracy,
        "home_baseline": home_baseline,
        "edge": accuracy - home_baseline,
        "draw_rate": draw_rate,
        "over_under_accuracy": over_acc,
        "btts_accuracy": btts_acc,
        "log_loss": logloss,
        "n_with_odds": n_odds,
        "model_accuracy_odds_subset": model_acc_sub,
        "book_accuracy": book_acc,
        "model_log_loss_odds_subset": model_ll_sub,
        "book_log_loss": book_ll,
        "_frame": res,
    }


def calibration_table(res: pd.DataFrame, n_bins: int = 10) -> list[dict]:
    """Reliability over pooled H/D/A forecasts.

    Every match contributes three (predicted probability, happened?) pairs.
    A well-calibrated model has observed frequency ~ mean predicted in each bin.
    """
    preds = np.concatenate([res["p_h"], res["p_d"], res["p_a"]])
    hit = np.concatenate([
        (res["actual"] == "H").astype(int),
        (res["actual"] == "D").astype(int),
        (res["actual"] == "A").astype(int),
    ])

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (preds >= lo) & (preds < hi) if i < n_bins - 1 else (preds >= lo) & (preds <= hi)
        n = int(mask.sum())
        if n == 0:
            rows.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": 0,
                         "mean_predicted": None, "observed": None, "gap": None})
            continue
        mp = float(preds[mask].mean())
        ob = float(hit[mask].mean())
        rows.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": n,
                     "mean_predicted": mp, "observed": ob, "gap": ob - mp})
    return rows


def _fmt(x, pct=False, places=3):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x * 100:.1f}%" if pct else f"{x:.{places}f}"


def main(codes: list[str] | None = None) -> int:
    codes = codes or [lg.code for lg in ACTIVE]
    print(f"Walk-forward backtest: {len(codes)} leagues")
    print(f"refit every {REFIT_DAYS}d | train window {TRAIN_WINDOW_DAYS}d | "
          f"half-life {HALF_LIFE_DAYS:.0f}d | min history {MIN_TRAIN_DAYS}d\n")

    results = []
    started = time.time()
    for code in codes:
        print(f"[{code}] downloading + backtesting...")
        try:
            r = backtest_league(code)
        except Exception as exc:  # noqa: BLE001
            print(f"  {code}: FAILED ({type(exc).__name__}: {exc})")
            continue
        if r:
            results.append(r)

    if not results:
        print("\nNo results produced.")
        return 1

    frames = pd.concat([r["_frame"] for r in results], ignore_index=True)
    for r in results:
        del r["_frame"]

    # ---------------- per-league table ----------------
    print("\n" + "=" * 118)
    print("PER-LEAGUE RESULTS  (walk-forward, out-of-sample)")
    print("=" * 118)
    head = (f"{'League':<18}{'N':>6}{'Acc':>8}{'HomeBase':>10}{'Edge':>8}"
            f"{'O/U 2.5':>9}{'BTTS':>8}{'LogLoss':>9}{'BookAcc':>9}{'BookLL':>9}{'vsBook':>9}")
    print(head)
    print("-" * 118)
    for r in sorted(results, key=lambda x: -x["accuracy"]):
        vs = (r["model_accuracy_odds_subset"] - r["book_accuracy"]
              if not np.isnan(r["book_accuracy"]) else float("nan"))
        print(f"{r['league']:<18}{r['n_predictions']:>6}"
              f"{_fmt(r['accuracy'], True):>8}{_fmt(r['home_baseline'], True):>10}"
              f"{_fmt(r['edge'], True):>8}{_fmt(r['over_under_accuracy'], True):>9}"
              f"{_fmt(r['btts_accuracy'], True):>8}{_fmt(r['log_loss']):>9}"
              f"{_fmt(r['book_accuracy'], True):>9}{_fmt(r['book_log_loss']):>9}"
              f"{_fmt(vs, True):>9}")

    # ---------------- pooled ----------------
    n_all = sum(r["n_predictions"] for r in results)
    probs = frames[["p_h", "p_d", "p_a"]].to_numpy(float)
    actual_idx = frames["actual"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy(int)
    pooled_acc = float((probs.argmax(axis=1) == actual_idx).mean())
    pooled_base = float((frames["actual"] == "H").mean())
    pooled_ll = _log_loss(probs, actual_idx)

    odds_mask = frames["book_h"].notna()
    sub = frames[odds_mask]
    if len(sub) >= 50:
        sp = sub[["p_h", "p_d", "p_a"]].to_numpy(float)
        sa = sub["actual"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy(int)
        bp = sub[["book_h", "book_d", "book_a"]].to_numpy(float)
        pooled_model_acc_sub = float((sp.argmax(axis=1) == sa).mean())
        pooled_book_acc = float((bp.argmax(axis=1) == sa).mean())
        pooled_model_ll_sub = _log_loss(sp, sa)
        pooled_book_ll = _log_loss(bp, sa)
    else:
        pooled_model_acc_sub = pooled_book_acc = pooled_model_ll_sub = pooled_book_ll = float("nan")

    print("-" * 118)
    print(f"{'ALL LEAGUES':<18}{n_all:>6}{_fmt(pooled_acc, True):>8}{_fmt(pooled_base, True):>10}"
          f"{_fmt(pooled_acc - pooled_base, True):>8}"
          f"{_fmt(float((frames['p_over'] >= 0.5).astype(int).eq(frames['over']).mean()), True):>9}"
          f"{_fmt(float((frames['p_btts'] >= 0.5).astype(int).eq(frames['btts']).mean()), True):>8}"
          f"{_fmt(pooled_ll):>9}{_fmt(pooled_book_acc, True):>9}{_fmt(pooled_book_ll):>9}"
          f"{_fmt(pooled_model_acc_sub - pooled_book_acc, True):>9}")

    # ---------------- calibration ----------------
    cal = calibration_table(frames)
    print("\n" + "=" * 118)
    print("CALIBRATION  (all leagues pooled; each match contributes its H, D and A forecast)")
    print("=" * 118)
    print(f"{'Predicted band':<18}{'N':>9}{'Mean predicted':>18}{'Observed':>12}{'Gap':>10}")
    print("-" * 118)
    for row in cal:
        if row["n"] == 0:
            print(f"{row['bin']:<18}{0:>9}{'-':>18}{'-':>12}{'-':>10}")
            continue
        print(f"{row['bin']:<18}{row['n']:>9}{_fmt(row['mean_predicted'], True):>18}"
              f"{_fmt(row['observed'], True):>12}{row['gap'] * 100:>+9.1f}pp")

    draw_rate = float((frames["actual"] == "D").mean())
    print("\n" + "=" * 118)
    print(f"Draws were {draw_rate * 100:.1f}% of all settled matches "
          f"({int((frames['actual'] == 'D').sum())} of {len(frames)}).")
    print(f"Total runtime: {(time.time() - started) / 60:.1f} min")
    print("=" * 118)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "settings": {
            "refit_days": REFIT_DAYS, "min_train_days": MIN_TRAIN_DAYS,
            "train_window_days": TRAIN_WINDOW_DAYS, "half_life_days": HALF_LIFE_DAYS,
            "min_team_matches": MIN_TEAM_MATCHES,
        },
        "leagues": results,
        "pooled": {
            "n": n_all, "accuracy": pooled_acc, "home_baseline": pooled_base,
            "edge": pooled_acc - pooled_base, "log_loss": pooled_ll,
            "draw_rate": draw_rate,
            "model_accuracy_odds_subset": pooled_model_acc_sub,
            "book_accuracy": pooled_book_acc,
            "model_log_loss_odds_subset": pooled_model_ll_sub,
            "book_log_loss": pooled_book_ll,
        },
        "calibration": cal,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nWritten to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
