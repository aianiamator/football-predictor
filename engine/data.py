"""Download and normalise historical results from football-data.co.uk.

No API key required. Raw CSVs are cached under data/raw/ so repeated runs and
backtests do not re-download. Completed seasons are cached permanently; the
current season is refreshed on demand.

Two upstream column eras have to be handled:
  * 2019/20 onward  -> AvgH / AvgD / AvgA   (market average closing odds)
  * up to 2018/19   -> BbAvH / BbAvD / BbAvA
B365H/D/A is the fallback when neither aggregate is present.

Everything downstream uses one canonical lowercase schema:

    league  date  home_team  away_team  home_goals  away_goals
    odds_home  odds_draw  odds_away  season

The odds columns exist ONLY as the bookmaker benchmark inside the backtest.
They are never published and never surfaced to a user.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
import requests

from .config import ACTIVE, BY_CODE, SEASONS
from .config import LEAGUES as _LEAGUE_OBJECTS

log = logging.getLogger(__name__)

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

# code -> (display name, flag emoji)
LEAGUES: dict[str, tuple[str, str]] = {lg.code: (lg.name, lg.flag) for lg in _LEAGUE_OBJECTS}

# The default set that gets fitted, backtested and published.
CORE_LEAGUES: list[str] = [lg.code for lg in ACTIVE]

# Preference order for the three-way market odds.
ODDS_SETS = [("AvgH", "AvgD", "AvgA"), ("BbAvH", "BbAvD", "BbAvA"), ("B365H", "B365D", "B365A")]

_SOURCE_CORE = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]

_RENAME = {
    "Div": "league",
    "Date": "date",
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG": "home_goals",
    "FTAG": "away_goals",
}


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
    if not set(_SOURCE_CORE).issubset(df.columns):
        log.warning("%s %s: missing core columns", code, season)
        return None

    out = df[_SOURCE_CORE].rename(columns=_RENAME).copy()
    out["date"] = _parse_dates(out["date"])

    for h, d, a in ODDS_SETS:
        if {h, d, a}.issubset(df.columns):
            out["odds_home"] = pd.to_numeric(df[h], errors="coerce")
            out["odds_draw"] = pd.to_numeric(df[d], errors="coerce")
            out["odds_away"] = pd.to_numeric(df[a], errors="coerce")
            break
    else:
        out["odds_home"] = out["odds_draw"] = out["odds_away"] = float("nan")

    out["season"] = season
    return out


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop unplayed/malformed rows and coerce types."""
    out = df.copy()
    out["home_goals"] = pd.to_numeric(out["home_goals"], errors="coerce")
    out["away_goals"] = pd.to_numeric(out["away_goals"], errors="coerce")
    out = out.dropna(subset=["date", "home_team", "away_team", "home_goals", "away_goals"])
    out["home_goals"] = out["home_goals"].astype(int)
    out["away_goals"] = out["away_goals"].astype(int)
    out["home_team"] = out["home_team"].astype(str).str.strip()
    out["away_team"] = out["away_team"].astype(str).str.strip()
    out = out[out["home_team"] != ""]
    out = out[out["away_team"] != ""]
    out = out[out["home_team"] != out["away_team"]]
    return out.sort_values("date").reset_index(drop=True)


def load_league(code: str, n_seasons: int = len(SEASONS), refresh_current: bool = True) -> pd.DataFrame:
    """All available completed matches for one league, oldest first."""
    seasons = SEASONS[-n_seasons:] if n_seasons else SEASONS
    frames = []
    for i, season in enumerate(seasons):
        is_last = i == len(seasons) - 1
        df = download_season(code, season, refresh=refresh_current and is_last)
        if df is not None and len(df):
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=list(_RENAME.values())
                            + ["odds_home", "odds_draw", "odds_away", "season"])
    return clean(pd.concat(frames, ignore_index=True))


def load_many(codes: list[str] | None = None, n_seasons: int = len(SEASONS),
              refresh_current: bool = True) -> pd.DataFrame:
    """Load several leagues into one frame."""
    codes = codes or CORE_LEAGUES
    frames = []
    for code in codes:
        df = load_league(code, n_seasons=n_seasons, refresh_current=refresh_current)
        if len(df):
            # Trust our own code, not the upstream Div field.
            df["league"] = code
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=list(_RENAME.values())
                            + ["odds_home", "odds_draw", "odds_away", "season"])
    return pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)


def implied_probabilities(odds_home, odds_draw, odds_away):
    """Decimal odds -> probabilities, with the overround normalised away.

    Returns (None, None, None) when any leg is missing or invalid.
    """
    try:
        h, d, a = float(odds_home), float(odds_draw), float(odds_away)
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
    cols = ["league", "date", "time", "home_team", "away_team"]
    try:
        resp = requests.get(FIXTURES_URL, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("fixtures download failed (%s)", exc)
        return pd.DataFrame(columns=cols)

    df = pd.read_csv(io.BytesIO(resp.content), encoding="utf-8-sig", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]
    if "Div" not in df.columns:
        return pd.DataFrame(columns=cols)

    rename = {"Div": "league", "Date": "date", "Time": "time",
              "HomeTeam": "home_team", "AwayTeam": "away_team"}
    keep = [c for c in rename if c in df.columns]
    out = df[keep].rename(columns=rename).copy()
    out["date"] = _parse_dates(out["date"])
    if "time" not in out.columns:
        out["time"] = ""
    out["time"] = out["time"].fillna("").astype(str)
    return out.dropna(subset=["date", "home_team", "away_team"]).reset_index(drop=True)


def league_name(code: str) -> str:
    return BY_CODE[code].name if code in BY_CODE else code
