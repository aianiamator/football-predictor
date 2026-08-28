"""Download and normalise historical results from football-data.co.uk.

No API key required. Raw CSVs are cached under data/raw/ so repeated runs and
backtests do not re-download. Completed seasons are cached permanently; the
current season is refreshed on demand.

Two column eras have to be handled:
  * 2019/20 onward  -> AvgH / AvgD / AvgA   (market average odds)
  * up to 2018/19   -> BbAvH / BbAvD / BbAvA
B365H/D/A is used as a fallback when neither aggregate is present.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
import requests

from .config import SEASONS

log = logging.getLogger(__name__)

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

# Preference order for the three-way market odds.
ODDS_SETS = [("AvgH", "AvgD", "AvgA"), ("BbAvH", "BbAvD", "BbAvA"), ("B365H", "B365D", "B365A")]

CORE = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]


def _parse_dates(s: pd.Series) -> pd.Series:
    """football-data uses dd/mm/yyyy, with dd/mm/yy in some older files."""
    out = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    missing = out.isna()
    if missing.any():
        out.loc[missing] = pd.to_datetime(s[missing], format="%d/%m/%y", errors="coerce")
    return out


def download_season(code: str, season: str, refresh: bool = False) -> pd.DataFrame | None:
    """Fetch one league-season, using the on-disk cache when possible."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cached = RAW_DIR / f"{season}_{code}.csv"

    if cached.exists() and not refresh:
        raw = cached.read_bytes()
    else:
        url = BASE_URL.format(season=season, code=code)
        try:
            resp = requests.get(url, timeout=60)
        except requests.RequestException as exc:
            log.warning("%s %s: download failed (%s)", code, season, exc)
            return None
        if resp.status_code != 200 or len(resp.content) < 200:
            log.warning("%s %s: unavailable (HTTP %s)", code, season, resp.status_code)
            return None
        raw = resp.content
        cached.write_bytes(raw)

    try:
        df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", on_bad_lines="skip")
    except Exception as exc:  # noqa: BLE001 - malformed upstream file
        log.warning("%s %s: parse failed (%s)", code, season, exc)
        return None

    df.columns = [c.strip() for c in df.columns]
    if not set(CORE).issubset(df.columns):
        log.warning("%s %s: missing core columns", code, season)
        return None

    out = df[CORE].copy()
    out["Date"] = _parse_dates(out["Date"])

    # Attach market odds from whichever era's columns are present.
    for h, d, a in ODDS_SETS:
        if {h, d, a}.issubset(df.columns):
            out["OddsH"] = pd.to_numeric(df[h], errors="coerce")
            out["OddsD"] = pd.to_numeric(df[d], errors="coerce")
            out["OddsA"] = pd.to_numeric(df[a], errors="coerce")
            break
    else:
        out["OddsH"] = out["OddsD"] = out["OddsA"] = pd.NA

    out["Season"] = season
    return out


def load_league(code: str, seasons: list[str] | None = None, refresh_current: bool = True) -> pd.DataFrame:
    """All available completed matches for one league, oldest first."""
    seasons = seasons or SEASONS
    frames = []
    for i, season in enumerate(seasons):
        is_last = i == len(seasons) - 1
        df = download_season(code, season, refresh=refresh_current and is_last)
        if df is not None and len(df):
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=[*CORE, "OddsH", "OddsD", "OddsA", "Season"])

    out = pd.concat(frames, ignore_index=True)
    return clean(out)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop unplayed/malformed rows and coerce types."""
    out = df.copy()
    out["FTHG"] = pd.to_numeric(out["FTHG"], errors="coerce")
    out["FTAG"] = pd.to_numeric(out["FTAG"], errors="coerce")
    out = out.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    out["FTHG"] = out["FTHG"].astype(int)
    out["FTAG"] = out["FTAG"].astype(int)
    out["HomeTeam"] = out["HomeTeam"].astype(str).str.strip()
    out["AwayTeam"] = out["AwayTeam"].astype(str).str.strip()
    out = out[out["HomeTeam"] != ""]
    out = out[out["AwayTeam"] != ""]
    out = out[out["HomeTeam"] != out["AwayTeam"]]

    # Derived outcome columns used by the model and the backtest.
    out["Result"] = "D"
    out.loc[out["FTHG"] > out["FTAG"], "Result"] = "H"
    out.loc[out["FTHG"] < out["FTAG"], "Result"] = "A"
    out["TotalGoals"] = out["FTHG"] + out["FTAG"]
    out["Over25"] = (out["TotalGoals"] >= 3).astype(int)
    out["BTTS"] = ((out["FTHG"] >= 1) & (out["FTAG"] >= 1)).astype(int)

    return out.sort_values("Date").reset_index(drop=True)


def implied_probabilities(odds_h, odds_d, odds_a):
    """Convert decimal odds to probabilities, normalising away the overround.

    Returns (None, None, None) when any leg is missing or invalid.
    """
    try:
        h, d, a = float(odds_h), float(odds_d), float(odds_a)
    except (TypeError, ValueError):
        return (None, None, None)
    if not all(x > 1.0 for x in (h, d, a)):
        return (None, None, None)
    raw = (1.0 / h, 1.0 / d, 1.0 / a)
    total = sum(raw)
    if total <= 0:
        return (None, None, None)
    return tuple(x / total for x in raw)


def load_fixtures() -> pd.DataFrame:
    """Upcoming fixtures published by football-data.co.uk."""
    try:
        resp = requests.get(FIXTURES_URL, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("fixtures download failed (%s)", exc)
        return pd.DataFrame(columns=["Div", "Date", "Time", "HomeTeam", "AwayTeam"])

    df = pd.read_csv(io.BytesIO(resp.content), encoding="utf-8-sig", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]
    if "Div" not in df.columns:
        return pd.DataFrame(columns=["Div", "Date", "Time", "HomeTeam", "AwayTeam"])

    keep = [c for c in ["Div", "Date", "Time", "HomeTeam", "AwayTeam"] if c in df.columns]
    out = df[keep].copy()
    out["Date"] = _parse_dates(out["Date"])
    if "Time" not in out.columns:
        out["Time"] = ""
    out["Time"] = out["Time"].fillna("").astype(str)
    return out.dropna(subset=["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)
