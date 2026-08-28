"""
Weekly prediction run.

Fits every league, predicts all upcoming fixtures, and writes output in a
shape the app can render directly — including plain-language labels and
visual cues, so the frontend never has to interpret numbers.

Run:  python -m engine.run
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import data as dataio
from .model import fit

OUT = Path(__file__).resolve().parent.parent / "output"

# Leagues where the over/under 2.5 edge cleared 2pp in backtesting.
# Everywhere else the market is not shown at all — a forecast that can't
# beat "always say over" by a visible margin is noise dressed as insight.
# Re-derive this list from backtest_summary.csv whenever you refit.
OVER_UNDER_LEAGUES = {"SP1", "P1"}

# Plain-language confidence bands.
#
# Thresholds are set from OBSERVED outcomes, not raw model output. Backtesting
# showed the top bands are overconfident: a stated 74% lands near 72%, a stated
# 93% near 82%. So "strong" starts at 0.70, not 0.65, and nothing above that
# gets stronger language — the model has not earned it.
def confidence_band(p: float) -> tuple[str, int, str]:
    if p >= 0.70:
        return "strong", 3, "#16a34a"
    if p >= 0.52:
        return "moderate", 2, "#ca8a04"
    return "close", 1, "#6b7280"


def plain_summary(pred: dict) -> str:
    """
    One short sentence, no jargon, readable at primary-school level.

    Never a single-outcome verdict. Across backtesting the model named a draw
    as most likely in 0.5% of matches while a quarter actually ended level, so
    any bare "X will win" sentence is misleading by construction. Every
    favourite sentence therefore carries the draw or the upset alongside it.
    """
    home, away = pred["home_team"], pred["away_team"]
    probs = {home: pred["home_win"], "draw": pred["draw"], away: pred["away_win"]}
    top = max(probs, key=probs.get)
    p = probs[top]
    draw_pct = round(pred["draw"] * 100)

    if top == "draw":
        return f"{home} and {away} look evenly matched. A draw is very possible."
    if p >= 0.70:
        return f"{top} are the strong favourite, but {draw_pct} in 100 games like this end in a draw."
    if p >= 0.52:
        return f"{top} are more likely to win. A draw is still common here."
    return f"{top} have a small edge, but this one is close and could go any way."


def build_fixture_payload(pred: dict, league_code: str, date, kickoff: str) -> dict:
    top_p = max(pred["home_win"], pred["draw"], pred["away_win"])
    band, stars, colour = confidence_band(top_p)
    league_name, country = dataio.LEAGUES.get(league_code, (league_code, ""))
    best = pred["likely_scorelines"][0]

    return {
        "league_code": league_code,
        "league": league_name,
        "country": country,
        "date": str(pd.to_datetime(date).date()),
        "kickoff": str(kickoff) if kickoff else "",
        "home_team": pred["home_team"],
        "away_team": pred["away_team"],
        # Percentages, pre-rounded so the UI never does maths.
        "home_win_pct": round(pred["home_win"] * 100),
        "draw_pct": round(pred["draw"] * 100),
        "away_win_pct": round(pred["away_win"] * 100),
        # Only published where backtesting showed a real edge over the
        # always-over baseline. None means the app hides the whole section.
        "over_2_5_pct": (
            round(pred["over_2_5"] * 100)
            if league_code in OVER_UNDER_LEAGUES
            else None
        ),
        # both_teams_score is deliberately NOT published. Its pooled edge over
        # baseline was +0.71pp with a Brier score worse than baseline, meaning
        # the forecast carries no information. Do not reinstate it without a
        # backtest showing a 2pp+ edge.
        "clean_sheet_home_pct": round(pred["clean_sheet_home"] * 100),
        "clean_sheet_away_pct": round(pred["clean_sheet_away"] * 100),
        "expected_goals_home": pred["expected_goals_home"],
        "expected_goals_away": pred["expected_goals_away"],
        "likely_score": f"{best['home_goals']}-{best['away_goals']}",
        "likely_scorelines": pred["likely_scorelines"],
        # Presentation helpers for a low-literacy UI.
        "confidence": band,
        "confidence_stars": stars,
        "confidence_colour": colour,
        "summary": plain_summary(pred),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def run(leagues: list[str] | None = None, n_seasons: int = 8) -> list[dict]:
    leagues = leagues or dataio.CORE_LEAGUES
    OUT.mkdir(exist_ok=True)

    print("Loading historical results...")
    history = dataio.load_many(leagues, n_seasons=n_seasons)
    if history.empty:
        raise SystemExit("No historical data available.")

    print("Loading upcoming fixtures...")
    fixtures = dataio.load_fixtures()
    if not fixtures.empty:
        # fixtures.csv keeps recently-played games for a few days. Publishing
        # those as forecasts would be wrong on its face and would collide with
        # the settle job, which owns everything already played.
        today = pd.Timestamp.now().normalize()
        before = len(fixtures)
        fixtures = fixtures[fixtures["date"] >= today]
        dropped = before - len(fixtures)
        if dropped:
            print(f"  ignored {dropped} fixture(s) already played")
    if fixtures.empty:
        print("No upcoming fixtures listed right now (common mid-week or off-season).")

    payloads: list[dict] = []
    ratings: list[dict] = []

    for league in leagues:
        league_history = history[history["league"] == league]
        if len(league_history) < 200:
            continue
        name = dataio.LEAGUES.get(league, (league,))[0]
        try:
            model = fit(league_history, league=league)
        except ValueError as exc:
            print(f"  {name}: skipped ({exc})")
            continue

        for team in model.teams:
            ratings.append(
                {
                    "league_code": league,
                    "league": name,
                    "team": team,
                    "attack": round(model.attack[team], 4),
                    "defence": round(model.defence[team], 4),
                    "overall": round(model.attack[team] + model.defence[team], 4),
                }
            )

        league_fixtures = fixtures[fixtures["league"] == league] if not fixtures.empty else pd.DataFrame()
        made = 0
        for _, fx in league_fixtures.iterrows():
            if not (model.knows(fx["home_team"]) and model.knows(fx["away_team"])):
                continue
            pred = model.predict(fx["home_team"], fx["away_team"])
            payloads.append(
                build_fixture_payload(pred, league, fx["date"], fx.get("kickoff", ""))
            )
            made += 1
        print(f"  {name}: {len(model.teams)} teams rated, {made} fixtures predicted")

    (OUT / "predictions.json").write_text(json.dumps(payloads, indent=2))
    (OUT / "ratings.json").write_text(json.dumps(ratings, indent=2))
    print(f"\nWrote {len(payloads)} predictions to {OUT / 'predictions.json'}")

    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"):
        push_to_supabase(payloads, ratings)
    else:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_KEY to publish to the app.")

    return payloads


def push_to_supabase(predictions: list[dict], ratings: list[dict]) -> None:
    """Upsert into Supabase. Service key is server-side only — never in the app."""
    import requests

    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_KEY"]
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    # PostgREST defaults an upsert's conflict target to the PRIMARY KEY. Here
    # that is a bigserial id which is never sent, so the merge could never
    # match and every re-run would fail on the unique constraint. Name the
    # real constraint columns explicitly.
    conflict = {
        "predictions": "league_code,date,home_team,away_team",
        "team_ratings": "league_code,team",
    }

    for table, rows in [("predictions", predictions), ("team_ratings", ratings)]:
        if not rows:
            continue
        for i in range(0, len(rows), 500):
            chunk = rows[i : i + 500]
            resp = requests.post(
                f"{url}/rest/v1/{table}?on_conflict={conflict[table]}",
                headers=headers, json=chunk, timeout=60
            )
            if resp.status_code >= 300:
                print(f"  ! {table} upsert failed: {resp.status_code} {resp.text[:200]}")
                return
        print(f"  pushed {len(rows)} rows to {table}")


if __name__ == "__main__":
    run()
