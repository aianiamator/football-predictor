"""
Downloads and normalises historical results from football-data.co.uk.

No API key, no registration. One CSV per league per season.
Everything is cached to disk so you only download each season once
(except the current one, which is refreshed).
"""

from __future__ import annotations

import io
import logging
import os
import time
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

BASE = "https://www.football-data.co.uk/mmz4281"
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

# code -> (display name, country, flag emoji)
# The flag is required by the app: every card and filter button carries one.
LEAGUES: dict[str, tuple[str, str, str]] = {
    "E0": ("Premier League", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
    "E1": ("Championship", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
    "E2": ("League One", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
    "E3": ("League Two", "England", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
    "SP1": ("La Liga", "Spain", "🇪🇸"),
    "SP2": ("La Liga 2", "Spain", "🇪🇸"),
    "I1": ("Serie A", "Italy", "🇮🇹"),
    "I2": ("Serie B", "Italy", "🇮🇹"),
    "D1": ("Bundesliga", "Germany", "🇩🇪"),
    "D2": ("Bundesliga 2", "Germany", "🇩🇪"),
    "F1": ("Ligue 1", "France", "🇫🇷"),
    "F2": ("Ligue 2", "France", "🇫🇷"),
    "N1": ("Eredivisie", "Netherlands", "🇳🇱"),
    "P1": ("Primeira Liga", "Portugal", "🇵🇹"),
    "B1": ("Pro League", "Belgium", "🇧🇪"),
    "T1": ("Super Lig", "Turkey", "🇹🇷"),
    "G1": ("Super League", "Greece", "🇬🇷"),
    "SC0": ("Premiership", "Scotland", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
}

# Leagues most watched by a Nigerian / diaspora audience, in priority order.
#
# Championship (E1) is deliberately excluded: backtesting over 3,216 matches
# gave only a +2.6pp edge over the always-home baseline, on the largest sample
# of the eight. It is a genuinely unpredictable league. Add it back only if a
# refit shows a 5pp+ edge.
CORE_LEAGUES = ["E0", "SP1", "I1", "D1", "F1", "N1", "P1"]

CACHE = Path(__file__).resolve().parent.parent / "data_cache"


def season_codes(n_seasons: int = 8, end_year: int | None = None) -> list[str]:
    """Recent season codes in football-data format, e.g. '2425' for 2024/25."""
    if end_year is None:
        now = pd.Timestamp.now()
        end_year = now.year if now.month >= 7 else now.year - 1
    codes = []
    for start in range(end_year - n_seasons + 1, end_year + 1):
        codes.append(f"{start % 100:02d}{(start + 1) % 100:02d}")
    return codes


class SourceUnavailable(RuntimeError):
    """The upstream feed could not be reached for a league we need.

    Raised rather than returning empty data, because an empty frame flows
    downstream and surfaces as an unreadable KeyError several functions later -
    which is exactly what happened: a transient block on the CI runner produced
    "KeyError: 'date'" in the leakage audit, telling nobody anything useful.
    """


# Politeness gap between requests to the same host. The feed is free and
# maintained by one person; hammering it is both rude and the fastest way to
# get an IP blocked - which is the most likely explanation for a run that
# works locally and fails on a shared CI runner.
REQUEST_GAP_SECONDS = 0.4
FETCH_ATTEMPTS = 3
_last_request = 0.0

# URLs that failed every attempt during the current job. The history snapshot
# means a blocked feed no longer empties the training data - which is good, but
# it also means a caller can no longer detect a block by finding no rows. Jobs
# that need FRESH data (settling results, listing fixtures) ask here instead of
# quietly succeeding on nine-year-old history.
_failed_urls: list[str] = []


def reset_fetch_failures() -> None:
    _failed_urls.clear()


def fetch_failures() -> list[str]:
    return list(_failed_urls)


def _polite_get(url: str) -> requests.Response:
    """One HTTP GET, spaced out from the previous one."""
    global _last_request
    gap = REQUEST_GAP_SECONDS - (time.time() - _last_request)
    if gap > 0:
        time.sleep(gap)
    _last_request = time.time()
    return requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})


def _fetch(url: str, cache_path: Path, max_age_hours: float | None) -> bytes | None:
    """Fetch one CSV, preferring a fresh-enough cache, retrying on failure.

    Returns None only when the file genuinely is not available - a season that
    has not started, say. A transient network failure is retried rather than
    being mistaken for "this season does not exist", which would silently
    shrink the training set and change every forecast.
    """
    if cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        if max_age_hours is None or age_h < max_age_hours:
            return cache_path.read_bytes()

    last_problem = "unknown"
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            resp = _polite_get(url)
        except requests.RequestException as exc:
            last_problem = f"{type(exc).__name__}"
        else:
            if resp.status_code == 200 and len(resp.content) >= 200:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(resp.content)
                return resp.content
            # 404 means the season file does not exist yet. That is a fact, not
            # a failure, so stop rather than retrying three times for nothing.
            if resp.status_code == 404:
                return cache_path.read_bytes() if cache_path.exists() else None
            last_problem = f"HTTP {resp.status_code}"

        if attempt < FETCH_ATTEMPTS:
            time.sleep(2 ** attempt)   # 2s, then 4s

    log.warning("%s: %s after %d attempts", url, last_problem, FETCH_ATTEMPTS)
    _failed_urls.append(f"{url} ({last_problem})")
    if os.environ.get("GITHUB_ACTIONS"):
        # Surface the HTTP-client view as a run annotation. The workflow's curl
        # probe says whether the host answers at all; this says what Python saw
        # for the same host. If curl gets 200 and requests does not, the block
        # is on the client, not the network.
        print(f"::error title=feed fetch failed::{url} -> {last_problem} "
              f"after {FETCH_ATTEMPTS} attempts", flush=True)
    # A stale cache beats nothing at all.
    return cache_path.read_bytes() if cache_path.exists() else None


def _read_csv(raw: bytes) -> pd.DataFrame:
    """Read one football-data CSV.

    These files carry a UTF-8 BOM. Decoded as latin-1 the BOM survives into the
    first column name, so a plain {"Div", ...}.issubset(df.columns) check fails
    and the caller silently returns nothing. Prefer utf-8-sig, fall back to
    latin-1 for the occasional accented team name, and strip any BOM left over.
    """
    try:
        df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", on_bad_lines="skip")
    except UnicodeDecodeError:
        df = pd.read_csv(io.BytesIO(raw), encoding="latin-1", on_bad_lines="skip")
    df.columns = [str(c).strip().lstrip("﻿").lstrip("ï»¿") for c in df.columns]
    return df


def _parse(raw: bytes, league: str, season: str) -> pd.DataFrame:
    df = _read_csv(raw)
    needed = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not needed.issubset(df.columns):
        return pd.DataFrame()

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["Date"], dayfirst=True, errors="coerce"),
            "home_team": df["HomeTeam"].astype(str).str.strip(),
            "away_team": df["AwayTeam"].astype(str).str.strip(),
            "home_goals": pd.to_numeric(df["FTHG"], errors="coerce"),
            "away_goals": pd.to_numeric(df["FTAG"], errors="coerce"),
        }
    )
    # Closing bookmaker odds, where present — used to benchmark the model.
    for col, name in [
        ("AvgCH", "odds_home"), ("AvgCD", "odds_draw"), ("AvgCA", "odds_away"),
        ("B365CH", "odds_home"), ("B365CD", "odds_draw"), ("B365CA", "odds_away"),
        ("AvgH", "odds_home"), ("AvgD", "odds_draw"), ("AvgA", "odds_away"),
    ]:
        if col in df.columns and name not in out.columns:
            out[name] = pd.to_numeric(df[col], errors="coerce")

    out["league"] = league
    out["season"] = season
    return out.dropna(subset=["date", "home_goals", "away_goals"])


HISTORY = Path(__file__).resolve().parent.parent / "data" / "history.csv.gz"
_history_cache: pd.DataFrame | None = None


def history() -> pd.DataFrame:
    """Finished seasons, read from the committed snapshot.

    A season that has ended never changes, but the engine used to re-download
    eight years of them on every run: 56 files, five times a day, from a free
    site maintained by one person. That is both wasteful and the most likely
    reason the CI runner started being refused. The snapshot removes those
    requests entirely, leaving only the season actually in progress.

    Regenerate it with:  python -m scripts.build_history
    """
    global _history_cache
    if _history_cache is None:
        if not HISTORY.exists():
            log.warning("no history snapshot at %s; falling back to downloads", HISTORY)
            _history_cache = pd.DataFrame()
        else:
            df = pd.read_csv(HISTORY, compression="gzip", parse_dates=["date"])
            df["season"] = df["season"].astype(str).str.zfill(4)
            # A CSV round-trip turns the goal columns into floats. Every value
            # is unchanged, but the model's input dtype should not depend on
            # whether a season came from the snapshot or the network.
            for col in ("home_goals", "away_goals"):
                df[col] = df[col].astype("int64")
            _history_cache = df
    return _history_cache


def load_league(league: str, n_seasons: int = 8) -> pd.DataFrame:
    """All available results for one league across recent seasons.

    Finished seasons come from the committed snapshot; only the season in
    progress is fetched. Any finished season the snapshot happens to be missing
    still falls back to a download, so a stale snapshot degrades gracefully
    rather than silently shrinking the training set.
    """
    frames = []
    codes = season_codes(n_seasons)
    current, finished = codes[-1], codes[:-1]

    hist = history()
    if not hist.empty:
        have = hist[(hist["league"] == league) & (hist["season"].isin(finished))]
        if not have.empty:
            frames.append(have)
            finished = [s for s in finished if s not in set(have["season"])]

    for season in finished + [current]:
        raw = _fetch(
            f"{BASE}/{season}/{league}.csv",
            CACHE / season / f"{league}.csv",
            max_age_hours=6 if season == current else None,
        )
        if raw:
            parsed = _parse(raw, league, season)
            if not parsed.empty:
                frames.append(parsed)
    if not frames:
        return pd.DataFrame()
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values("date")
        .reset_index(drop=True)
    )


def load_many(leagues: list[str] | None = None, n_seasons: int = 8,
              require: bool = True) -> pd.DataFrame:
    """Load several leagues.

    An individual league may legitimately be empty - a season file that has not
    been created yet. But if EVERY league comes back empty the feed is
    unreachable, and continuing would train on nothing and publish nonsense. So
    that case raises instead of returning an empty frame for someone else to
    trip over three functions later.
    """
    leagues = leagues or CORE_LEAGUES
    frames, missing = [], []
    for lg in leagues:
        df = load_league(lg, n_seasons)
        if df.empty:
            missing.append(lg)
            print(f"  ! no data for {lg}")
        else:
            print(f"  {LEAGUES.get(lg, (lg,))[0]}: {len(df)} matches")
            frames.append(df)

    if require and not frames:
        raise SourceUnavailable(
            f"football-data.co.uk returned nothing for any of {leagues}. "
            "The feed is unreachable or blocking this host; this is an "
            "infrastructure problem, not a modelling one. Nothing was published."
        )
    if missing:
        log.warning("no data for %s", ", ".join(missing))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_fixtures() -> pd.DataFrame:
    """Upcoming fixtures for the next week or so, all leagues."""
    raw = _fetch(FIXTURES_URL, CACHE / "fixtures.csv", max_age_hours=3)
    if not raw:
        # An empty frame here is indistinguishable from "no matches scheduled",
        # and the caller used to print exactly that - blaming the calendar for
        # a blocked feed and finishing green with nothing published. Say which
        # it is.
        raise SourceUnavailable(
            "The fixture list could not be downloaded. Without it there is "
            "nothing to forecast. This is a network problem, not an empty "
            "calendar.")
    df = _read_csv(raw)
    if not {"Div", "Date", "HomeTeam", "AwayTeam"}.issubset(df.columns):
        return pd.DataFrame()
    out = pd.DataFrame(
        {
            "league": df["Div"].astype(str).str.strip(),
            "date": pd.to_datetime(df["Date"], dayfirst=True, errors="coerce"),
            "kickoff": df["Time"] if "Time" in df.columns else "",
            "home_team": df["HomeTeam"].astype(str).str.strip(),
            "away_team": df["AwayTeam"].astype(str).str.strip(),
        }
    )
    return out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
