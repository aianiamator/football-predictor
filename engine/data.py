"""
Downloads and normalises historical results from football-data.co.uk.

No API key, no registration. One CSV per league per season.
Everything is cached to disk so you only download each season once
(except the current one, which is refreshed).
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import requests

BASE = "https://www.football-data.co.uk/mmz4281"
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

# code -> (display name, country)
LEAGUES: dict[str, tuple[str, str]] = {
    "E0": ("Premier League", "England"),
    "E1": ("Championship", "England"),
    "E2": ("League One", "England"),
    "E3": ("League Two", "England"),
    "SP1": ("La Liga", "Spain"),
    "SP2": ("La Liga 2", "Spain"),
    "I1": ("Serie A", "Italy"),
    "I2": ("Serie B", "Italy"),
    "D1": ("Bundesliga", "Germany"),
    "D2": ("Bundesliga 2", "Germany"),
    "F1": ("Ligue 1", "France"),
    "F2": ("Ligue 2", "France"),
    "N1": ("Eredivisie", "Netherlands"),
    "P1": ("Primeira Liga", "Portugal"),
    "B1": ("Pro League", "Belgium"),
    "T1": ("Super Lig", "Turkey"),
    "G1": ("Super League", "Greece"),
    "SC0": ("Premiership", "Scotland"),
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


def _fetch(url: str, cache_path: Path, max_age_hours: float | None) -> bytes | None:
    if cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        if max_age_hours is None or age_h < max_age_hours:
            return cache_path.read_bytes()
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200 or len(resp.content) < 200:
            return cache_path.read_bytes() if cache_path.exists() else None
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(resp.content)
        return resp.content
    except requests.RequestException:
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


def load_league(league: str, n_seasons: int = 8) -> pd.DataFrame:
    """All available results for one league across recent seasons."""
    frames = []
    codes = season_codes(n_seasons)
    for i, season in enumerate(codes):
        is_current = i == len(codes) - 1
        raw = _fetch(
            f"{BASE}/{season}/{league}.csv",
            CACHE / season / f"{league}.csv",
            max_age_hours=6 if is_current else None,
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


def load_many(leagues: list[str] | None = None, n_seasons: int = 8) -> pd.DataFrame:
    leagues = leagues or CORE_LEAGUES
    frames = []
    for lg in leagues:
        df = load_league(lg, n_seasons)
        if df.empty:
            print(f"  ! no data for {lg}")
        else:
            print(f"  {LEAGUES.get(lg, (lg,))[0]}: {len(df)} matches")
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_fixtures() -> pd.DataFrame:
    """Upcoming fixtures for the next week or so, all leagues."""
    raw = _fetch(FIXTURES_URL, CACHE / "fixtures.csv", max_age_hours=3)
    if not raw:
        return pd.DataFrame()
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
