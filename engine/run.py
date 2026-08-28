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

from zoneinfo import ZoneInfo

from . import data as dataio
from . import store
from .model import fit

# football-data publishes kick-off times in UK local time. Nigeria is UTC+1 all
# year, the UK is UTC+0 in winter, so from late October to late March a raw time
# is an hour early for the audience. Everything is published as UTC and the app
# renders it in the reader's own zone.
SOURCE_TZ = ZoneInfo("Europe/London")

# Where the published JSON is written. On a server, point this straight at the
# directory nginx serves, so there is no copy step that can silently fail and
# leave the site showing last week's forecasts.
OUT = Path(os.getenv("FORECAST_OUT", Path(__file__).resolve().parent.parent / "output"))

# Leagues where over/under 2.5 is shown at all. Everywhere else the section is
# hidden entirely — a forecast that cannot beat "always say over" by a visible
# margin is noise dressed as insight.
#
# Two tests must BOTH pass: the forecast beats the always-majority baseline by
# 2pp or more, AND its probabilities score better than baseline (Brier). Ligue 1
# clears the first (+2.52pp) but fails the second, so it is excluded: picking the
# right side slightly more often with worse probabilities is luck, not signal.
# Re-derive from backtest_summary.csv whenever you refit.
OVER_UNDER_LEAGUES = {"P1", "SP1", "I1", "E0"}

# Plain-language confidence bands.
#
# Thresholds are set from OBSERVED outcomes, not raw model output. Backtesting
# showed the top bands are overconfident: a stated 74% lands near 72%, a stated
# 93% near 82%. So "strong" starts at 0.70, not 0.65, and nothing above that
# gets stronger language — the model has not earned it.
# Colours are chosen so that grey never means two things at once: the draw
# segment of the three-way bar is a COOL slate, so low confidence here is a
# WARM stone. All three pass contrast on a cheap screen in daylight.
def confidence_band(p: float) -> tuple[str, int, str]:
    if p >= 0.70:
        return "strong", 3, "#15803d"    # green
    if p >= 0.52:
        return "moderate", 2, "#b45309"  # amber
    return "close", 1, "#78716c"         # warm stone


def kickoff_to_utc(date, kickoff: str) -> str | None:
    """Combine a match date and UK local kick-off into a UTC timestamp."""
    if not kickoff or ":" not in str(kickoff):
        return None
    try:
        hh, mm = str(kickoff).split(":")[:2]
        naive = pd.Timestamp(date).normalize() + pd.Timedelta(hours=int(hh), minutes=int(mm))
        local = naive.tz_localize(SOURCE_TZ, nonexistent="shift_forward", ambiguous=True)
        return local.tz_convert("UTC").isoformat()
    except (ValueError, TypeError):
        return None


def summarise_outcome(pred: dict) -> tuple[str, dict, str]:
    """Return (key, arguments, English sentence).

    The app rebuilds this sentence in the reader's language from the key and
    the arguments. It must never have to parse the English text, which would
    break the moment any wording changed.

    Never a single-outcome verdict. Across backtesting the model named a draw
    as most likely in 0.5% of matches while a quarter actually ended level, so
    a bare "X will win" is misleading by construction. Every favourite sentence
    therefore carries the draw or the upset alongside it.
    """
    home, away = pred["home_team"], pred["away_team"]
    probs = {home: pred["home_win"], "draw": pred["draw"], away: pred["away_win"]}
    top = max(probs, key=probs.get)
    p = probs[top]
    draw_pct = round(pred["draw"] * 100)

    if top == "draw":
        return ("evenly_matched", {"home": home, "away": away},
                f"{home} and {away} look evenly matched. A draw is very possible.")
    if p >= 0.70:
        return ("strong_favourite", {"team": top, "draw_pct": draw_pct},
                f"{top} are the strong favourite, but {draw_pct} in 100 games "
                f"like this end in a draw.")
    if p >= 0.52:
        return ("more_likely", {"team": top},
                f"{top} are more likely to win. A draw is still common here.")
    return ("small_edge", {"team": top},
            f"{top} have a small edge, but this one is close and could go any way.")


def plain_summary(pred: dict) -> str:
    """English sentence only. Kept for the speech fallback and for tests."""
    return summarise_outcome(pred)[2]


def build_fixture_payload(pred: dict, league_code: str, date, kickoff: str) -> dict:
    top_p = max(pred["home_win"], pred["draw"], pred["away_win"])
    band, stars, colour = confidence_band(top_p)
    league_name, country, flag = dataio.LEAGUES.get(league_code, (league_code, "", ""))
    best = pred["likely_scorelines"][0]
    summary_key, summary_args, summary_text = summarise_outcome(pred)

    return {
        "league_code": league_code,
        "league": league_name,
        "country": country,
        "date": str(pd.to_datetime(date).date()),
        "kickoff": str(kickoff) if kickoff else "",
        # UTC, so the app can render the time in the reader's own zone.
        "kickoff_utc": kickoff_to_utc(date, kickoff),
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
        "summary": summary_text,
        # Structured form, so translation never parses English prose.
        "summary_key": summary_key,
        "summary_args": summary_args,
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

    # The durable store first, then the static files derived from it.
    conn = store.connect()
    try:
        counts = store.upsert_predictions(conn, payloads)
        n_ratings = store.upsert_ratings(conn, ratings)
        print(f"\nStore: {counts['inserted']} new, {counts['refreshed']} refreshed, "
              f"{counts['frozen']} left frozen (already settled), "
              f"{n_ratings} team ratings")

        published = store.publish_json(conn, OUT)
        print(f"Published: {published['upcoming']} upcoming, "
              f"{published['settled']} settled, {published['leagues']} leagues in record")
        for name in ("predictions.json", "track-record.json", "meta.json"):
            size = (OUT / name).stat().st_size
            print(f"  {name:<20}{size / 1024:7.1f} KB")
        print(f"\nStore:  {store.DB_PATH}")
        print(f"Static: {OUT}   <- this directory is what Cloudflare serves")
    finally:
        conn.close()

    return payloads


if __name__ == "__main__":
    run()
