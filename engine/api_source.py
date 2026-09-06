"""Fixtures and results from api.football-data.org.

Why this exists
---------------
football-data.co.uk serves 503 to GitHub's runners. Verified in the same
minute: 200 from a home connection, 503 from Actions, for every URL including
the site's own homepage. Those addresses are shared by thousands of projects
scraping the same free site, so behaving well ourselves cannot lift it.

This is a real API with a free tier covering exactly the seven leagues the app
forecasts. It is called, not scraped, so it will not ban us for showing up.

What it does NOT do
-------------------
It does not replace the history snapshot. Nine years of finished seasons still
come from data/history.csv.gz, and the model is fitted on exactly the same
matches as before. This supplies only the two things that must be current:
upcoming fixtures, and results for matches that have just been played.

The name problem
----------------
The two sources name teams differently - "Man United" against "Manchester
United FC". Every stored forecast is keyed by the football-data.co.uk name, so
a result arriving under a different name would either fail to settle or, far
worse, settle against the wrong fixture. So this module never guesses: an
unrecognised name raises. Mapping lives in data/team_aliases.json and is
checked by scripts/check_api.py.
"""
from __future__ import annotations

import json
import os
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests

# football-data.co.uk publishes kick-offs in UK local time and the rest of the
# engine assumes that, so API times are converted into it rather than the other
# way round. Changing the convention would re-date historical forecasts.
UK = "Europe/London"

BASE = "https://api.football-data.org/v4"
ALIASES = Path(__file__).resolve().parent.parent / "data" / "team_aliases.json"

# Our league code -> the API's competition code.
COMPETITIONS = {
    "E0": "PL",     # Premier League
    "SP1": "PD",    # Primera Division / La Liga
    "I1": "SA",     # Serie A
    "D1": "BL1",    # Bundesliga
    "F1": "FL1",    # Ligue 1
    "N1": "DED",    # Eredivisie
    "P1": "PPL",    # Primeira Liga
}

# The free tier allows 10 requests a minute. A full run needs 14 (fixtures and
# results for seven leagues), so pace them rather than being throttled midway
# and leaving half the leagues unsettled.
MIN_GAP_SECONDS = 6.5
TIMEOUT = 30
ATTEMPTS = 3

_last_call = 0.0


class ApiUnavailable(RuntimeError):
    """The API could not be reached, or refused us."""


class UnknownTeam(RuntimeError):
    """A team name with no mapping to the name our forecasts are stored under.

    Deliberately fatal. Silently skipping would leave a forecast permanently
    'awaiting a result'; silently guessing could settle it against a different
    match. Both are worse than a loud stop.
    """


def token() -> str:
    tok = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not tok:
        raise ApiUnavailable(
            "FOOTBALL_DATA_TOKEN is not set. Locally it belongs in .env "
            "(which is git-ignored); in CI it is a repository secret. It is "
            "never written into a file that could be committed.")
    return tok


def _get(path: str, params: dict | None = None) -> dict:
    """One paced, retried API call."""
    global _last_call
    last = "unknown"
    for attempt in range(1, ATTEMPTS + 1):
        gap = MIN_GAP_SECONDS - (time.time() - _last_call)
        if gap > 0:
            time.sleep(gap)
        _last_call = time.time()
        try:
            r = requests.get(f"{BASE}/{path}", params=params or {},
                             headers={"X-Auth-Token": token()}, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last = type(exc).__name__
        else:
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 403, 404):
                # A wrong token or a competition outside the free tier will not
                # come right by asking again.
                raise ApiUnavailable(f"{path}: HTTP {r.status_code} - {r.text[:200]}")
            last = f"HTTP {r.status_code}"       # 429 or 5xx: worth retrying
        if attempt < ATTEMPTS:
            time.sleep(5 * attempt)
    raise ApiUnavailable(f"{path}: {last} after {ATTEMPTS} attempts")


def normalise(name: str) -> str:
    """A loose key for matching names across the two sources.

    Strips accents, punctuation and the club suffixes the two sources disagree
    about. Used only to PROPOSE a mapping for review - never to accept one at
    run time, because "Real Sociedad" and "Real Madrid" both survive this
    treatment as distinct but similar keys, and near-misses are exactly the
    error we cannot afford.
    """
    s = unicodedata.normalize("NFKD", name.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    for word in (" fc", " afc", " cf", " sc", " ac", " ss", " as", " sv",
                 " bv", " vfl", " vfb", " tsg", " fsv", " rc", " ud", " cd",
                 "fc ", "sc ", "ac ", "as ", "rc ", "sv "):
        s = s.replace(word, " ")
    return "".join(c for c in s if c.isalnum())


def aliases() -> dict[str, str]:
    """API team name -> the name our forecasts are stored under."""
    if not ALIASES.exists():
        return {}
    return json.loads(ALIASES.read_text(encoding="utf-8"))


def to_store_name(api_name: str, table: dict[str, str] | None = None) -> str:
    table = aliases() if table is None else table
    if api_name in table:
        return table[api_name]
    raise UnknownTeam(
        f"No mapping for {api_name!r}. Add it to data/team_aliases.json - "
        f"run 'python -m scripts.check_api' to regenerate the proposals. "
        f"Refusing to guess, because a wrong mapping settles a forecast "
        f"against the wrong match.")


def _rows(payload: dict, league: str, table: dict[str, str],
          finished: bool) -> list[dict]:
    out = []
    for m in payload.get("matches", []):
        score = (m.get("score") or {}).get("fullTime") or {}
        if finished and (score.get("home") is None or score.get("away") is None):
            continue
        kickoff = pd.Timestamp(m["utcDate"])
        # The API states kick-off in UTC; football-data.co.uk states it in UK
        # local time, and build_fixture_payload converts UK local -> UTC. Handing
        # it a UTC time would put every kick-off an hour out through British
        # summer time, so give it the UK-local form it expects AND the UTC value
        # to use directly. `date` stays the UK-local calendar date, because that
        # is the date every existing forecast is stored under.
        local = kickoff.tz_convert(UK)
        row = {
            "league": league,
            "date": local.tz_localize(None).normalize(),
            "kickoff_utc": kickoff.isoformat(),
            "kickoff": local.strftime("%H:%M"),
            "home_team": to_store_name(m["homeTeam"]["name"], table),
            "away_team": to_store_name(m["awayTeam"]["name"], table),
            "status": m["status"],
        }
        if finished:
            row["home_goals"] = int(score["home"])
            row["away_goals"] = int(score["away"])
        out.append(row)
    return out


def fixtures(leagues: list[str] | None = None, days: int = 10) -> pd.DataFrame:
    """Scheduled matches in the next `days` days, in our own column names."""
    leagues = leagues or list(COMPETITIONS)
    table = aliases()
    today = pd.Timestamp.utcnow().normalize()
    rows: list[dict] = []
    for lg in leagues:
        data = _get(f"competitions/{COMPETITIONS[lg]}/matches", {
            "dateFrom": today.strftime("%Y-%m-%d"),
            "dateTo": (today + pd.Timedelta(days=days)).strftime("%Y-%m-%d"),
            "status": "SCHEDULED,TIMED",
        })
        rows += _rows(data, lg, table, finished=False)
    return pd.DataFrame(rows)


def results(leagues: list[str] | None = None, days_back: int = 14) -> pd.DataFrame:
    """Finished matches in the last `days_back` days."""
    leagues = leagues or list(COMPETITIONS)
    table = aliases()
    today = pd.Timestamp.utcnow().normalize()
    rows: list[dict] = []
    for lg in leagues:
        data = _get(f"competitions/{COMPETITIONS[lg]}/matches", {
            "dateFrom": (today - pd.Timedelta(days=days_back)).strftime("%Y-%m-%d"),
            "dateTo": today.strftime("%Y-%m-%d"),
            "status": "FINISHED",
        })
        rows += _rows(data, lg, table, finished=True)
    return pd.DataFrame(rows)
