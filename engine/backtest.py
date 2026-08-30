"""
Walk-forward backtest.

For every matchday, the model is fitted ONLY on matches played before it,
then used to predict that day's games. No future information leaks in.
This is the number you can publish honestly.

Run:  python -m engine.backtest
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import data as dataio
from .model import fit


def _outcome(row) -> str:
    if row["home_goals"] > row["away_goals"]:
        return "H"
    if row["home_goals"] < row["away_goals"]:
        return "A"
    return "D"


def backtest_league(
    matches: pd.DataFrame,
    league: str,
    min_train_matches: int = 400,
    refit_every_days: int = 7,
    xi: float = 0.0018,
    ridge: float | None = None,
) -> pd.DataFrame:
    matches = matches[matches["league"] == league].copy()
    if len(matches) < min_train_matches + 100:
        return pd.DataFrame()

    matches["date"] = pd.to_datetime(matches["date"])
    matches = matches.sort_values("date").reset_index(drop=True)

    start_date = matches.loc[min_train_matches, "date"]
    test = matches[matches["date"] > start_date]

    rows = []
    model = None
    last_fit = None

    for date, day_matches in test.groupby("date"):
        if last_fit is None or (date - last_fit).days >= refit_every_days:
            train = matches[matches["date"] < date]
            if len(train) < min_train_matches:
                continue
            try:
                model = (fit(train, xi=xi, league=league, reference_date=date)
                         if ridge is None else
                         fit(train, xi=xi, league=league, reference_date=date, ridge=ridge))
            except ValueError:
                continue
            last_fit = date

        if model is None:
            continue

        for _, m in day_matches.iterrows():
            if not (model.knows(m["home_team"]) and model.knows(m["away_team"])):
                continue
            p = model.predict(m["home_team"], m["away_team"])
            actual = _outcome(m)
            probs = {"H": p["home_win"], "D": p["draw"], "A": p["away_win"]}
            rows.append(
                {
                    "league": league,
                    "date": date,
                    "home_team": m["home_team"],
                    "away_team": m["away_team"],
                    "actual": actual,
                    "predicted": max(probs, key=probs.get),
                    "p_actual": probs[actual],
                    "p_max": max(probs.values()),
                    "p_home": probs["H"],
                    "p_draw": probs["D"],
                    "p_away": probs["A"],
                    "total_goals": m["home_goals"] + m["away_goals"],
                    "p_over_25": p["over_2_5"],
                    "btts_actual": int(m["home_goals"] > 0 and m["away_goals"] > 0),
                    "p_btts": p["both_teams_score"],
                    "odds_home": m.get("odds_home", np.nan),
                    "odds_draw": m.get("odds_draw", np.nan),
                    "odds_away": m.get("odds_away", np.nan),
                }
            )

    return pd.DataFrame(rows)


def summarise(results: pd.DataFrame) -> dict:
    if results.empty:
        return {}

    n = len(results)
    acc = float((results["predicted"] == results["actual"]).mean())
    log_loss = float(-np.log(np.clip(results["p_actual"], 1e-9, 1)).mean())

    # Every market is judged against the best you could do WITHOUT a model,
    # which is always calling the majority class. A raw accuracy figure with
    # no baseline beside it is meaningless and must never be published alone.
    over_actual = results["total_goals"] > 2.5
    over_correct = float(((results["p_over_25"] > 0.5) == over_actual).mean())
    over_rate = float(over_actual.mean())
    over_baseline = max(over_rate, 1.0 - over_rate)  # always-over or always-under

    btts_actual = results["btts_actual"] == 1
    btts_correct = float(((results["p_btts"] > 0.5) == btts_actual).mean())
    btts_rate = float(btts_actual.mean())
    btts_baseline = max(btts_rate, 1.0 - btts_rate)

    # Home-bias baseline: what you'd get by always saying "home win".
    # (For 1X2, home is always the majority class in practice.)
    baseline = float((results["actual"] == "H").mean())

    # Brier scores for the two binary markets — the calibration equivalent
    # of log loss. Lower is better; compare against the baseline Brier.
    over_brier = float(((results["p_over_25"] - over_actual.astype(float)) ** 2).mean())
    over_brier_base = float(((over_rate - over_actual.astype(float)) ** 2).mean())
    btts_brier = float(((results["p_btts"] - btts_actual.astype(float)) ** 2).mean())
    btts_brier_base = float(((btts_rate - btts_actual.astype(float)) ** 2).mean())

    out = {
        "matches": n,
        "result_accuracy": round(acc, 4),
        "always_home_baseline": round(baseline, 4),
        "edge_over_baseline": round(acc - baseline, 4),
        "over_under_accuracy": round(over_correct, 4),
        "over_under_baseline": round(over_baseline, 4),
        "over_under_edge": round(over_correct - over_baseline, 4),
        "over_under_brier": round(over_brier, 4),
        "over_under_brier_baseline": round(over_brier_base, 4),
        "btts_accuracy": round(btts_correct, 4),
        "btts_baseline": round(btts_baseline, 4),
        "btts_edge": round(btts_correct - btts_baseline, 4),
        "btts_brier": round(btts_brier, 4),
        "btts_brier_baseline": round(btts_brier_base, 4),
        "log_loss": round(log_loss, 4),
        "draws_predicted": int((results["predicted"] == "D").sum()),
        "draws_actual": int((results["actual"] == "D").sum()),
    }

    # Bookmaker benchmark where closing odds exist.
    odds = results.dropna(subset=["odds_home", "odds_draw", "odds_away"])
    if len(odds) > 100:
        implied = pd.DataFrame(
            {
                "H": 1 / odds["odds_home"],
                "D": 1 / odds["odds_draw"],
                "A": 1 / odds["odds_away"],
            }
        )
        book_pick = implied.idxmax(axis=1)
        out["bookmaker_accuracy"] = round(
            float((book_pick.to_numpy() == odds["actual"].to_numpy()).mean()), 4
        )
        out["accuracy_vs_bookmaker"] = round(
            float(
                (odds["predicted"] == odds["actual"]).mean()
                - (book_pick.to_numpy() == odds["actual"].to_numpy()).mean()
            ),
            4,
        )
        # Strip the overround so the bookmaker's implied probabilities sum
        # to 1, otherwise its log loss is flattered by the built-in margin.
        normalised = implied.div(implied.sum(axis=1), axis=0)
        book_p_actual = normalised.to_numpy()[
            np.arange(len(odds)),
            [list("HDA").index(a) for a in odds["actual"]],
        ]
        out["bookmaker_log_loss"] = round(
            float(-np.log(np.clip(book_p_actual, 1e-9, 1)).mean()), 4
        )
        out["overround"] = round(float(implied.sum(axis=1).mean()), 4)
        out["bookmaker_sample"] = len(odds)

    return out


def calibration(results: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    """Does a stated 60% actually happen 60% of the time?"""
    stacked = pd.concat(
        [
            pd.DataFrame({"p": results["p_home"], "hit": results["actual"] == "H"}),
            pd.DataFrame({"p": results["p_draw"], "hit": results["actual"] == "D"}),
            pd.DataFrame({"p": results["p_away"], "hit": results["actual"] == "A"}),
        ]
    )
    stacked["bucket"] = (stacked["p"] * bins).clip(0, bins - 1).astype(int)
    grouped = stacked.groupby("bucket").agg(
        predicted=("p", "mean"), observed=("hit", "mean"), n=("p", "size")
    )
    grouped.index = [f"{i * 100 // bins}-{(i + 1) * 100 // bins}%" for i in grouped.index]
    return grouped.round(3)


def main() -> None:
    print("Downloading historical results (first run takes a minute)...")
    matches = dataio.load_many(dataio.CORE_LEAGUES, n_seasons=8)
    if matches.empty:
        print("No data downloaded. Check your internet connection.")
        return

    all_results = []
    summaries = []

    for league in dataio.CORE_LEAGUES:
        name = dataio.LEAGUES.get(league, (league, ""))[0]
        print(f"\nBacktesting {name}...", flush=True)
        res = backtest_league(matches, league)
        if res.empty:
            print("  not enough data")
            continue
        s = summarise(res)
        s["league"] = name
        summaries.append(s)
        all_results.append(res)
        print(
            f"  {s['matches']} matches\n"
            f"    1X2   {s['result_accuracy']:.1%} vs baseline "
            f"{s['always_home_baseline']:.1%}  ({s['edge_over_baseline']:+.1%})"
            + (
                f"  | bookmaker {s['bookmaker_accuracy']:.1%} "
                f"({s['accuracy_vs_bookmaker']:+.1%})"
                if "bookmaker_accuracy" in s
                else ""
            )
            + f"\n    O/U   {s['over_under_accuracy']:.1%} vs baseline "
            f"{s['over_under_baseline']:.1%}  ({s['over_under_edge']:+.1%})"
            f"\n    BTTS  {s['btts_accuracy']:.1%} vs baseline "
            f"{s['btts_baseline']:.1%}  ({s['btts_edge']:+.1%})"
        )

    if not summaries:
        return

    combined = pd.concat(all_results, ignore_index=True)
    table = pd.DataFrame(summaries).set_index("league")
    table.to_csv("backtest_summary.csv")
    combined.to_csv("backtest_predictions.csv", index=False)

    print("\n" + "=" * 62)
    print("OVERALL")
    print("=" * 62)
    overall = summarise(combined)
    for k, v in overall.items():
        print(f"  {k:<26} {v}")

    print("\nCALIBRATION (predicted vs what actually happened)")
    print(calibration(combined).to_string())

    print("\n" + "=" * 62)
    print("HOW TO READ THIS")
    print("=" * 62)
    print(
        "  Every accuracy figure is only meaningful next to its baseline —\n"
        "  the score you'd get with no model at all, by always calling the\n"
        "  majority outcome. Publish the edge, never the raw accuracy.\n"
    )
    if overall["edge_over_baseline"] < 0.03:
        print("  ! 1X2 edge is under 3pp. The model is barely beating a coin.")
    if overall["over_under_edge"] < 0.02:
        print("  ! Over/under edge is under 2pp. Do not present this market.")
    if overall["btts_edge"] < 0.02:
        print("  ! BTTS edge is under 2pp. Do not present this market.")
    if overall["result_accuracy"] > 0.60:
        print(
            "  !! Accuracy above 60% is not plausible for football.\n"
            "     Assume future information is leaking into training and\n"
            "     find the bug before publishing anything."
        )
    if "bookmaker_log_loss" in overall:
        gap = overall["log_loss"] - overall["bookmaker_log_loss"]
        print(
            f"  Log loss vs bookmaker: {gap:+.4f} "
            f"(overround stripped; bookmaker margin was "
            f"{(overall['overround'] - 1) * 100:.1f}%)"
        )
        if gap > 0:
            print(
                "  Losing to the closing line is the expected result on free\n"
                "  data. It is evidence the backtest is honest, not a failure."
            )

    weak = [
        s["league"]
        for s in summaries
        if s["edge_over_baseline"] < 0.05 or s["result_accuracy"] < 0.48
    ]
    if weak:
        print(
            "\n  Leagues with weak signal — consider dropping from the\n"
            "  default set in engine/data.py CORE_LEAGUES:\n    "
            + ", ".join(weak)
        )

    print("\nSaved: backtest_summary.csv, backtest_predictions.csv")


if __name__ == "__main__":
    main()
