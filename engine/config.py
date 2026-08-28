"""League configuration and shared constants.

18 leagues are configured; 8 are active. Active leagues are the ones fitted,
backtested and published. The rest are wired up but switched off so they can be
enabled without code changes.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    code: str          # football-data.co.uk division code
    name: str          # display name
    country: str
    flag: str          # emoji, used by the app
    active: bool


LEAGUES: list[League] = [
    # --- active ---
    League("E0",  "Premier League",   "England",     "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F", True),
    League("E1",  "Championship",     "England",     "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F", True),
    League("D1",  "Bundesliga",       "Germany",     "\U0001F1E9\U0001F1EA", True),
    League("I1",  "Serie A",          "Italy",       "\U0001F1EE\U0001F1F9", True),
    League("SP1", "La Liga",          "Spain",       "\U0001F1EA\U0001F1F8", True),
    League("F1",  "Ligue 1",          "France",      "\U0001F1EB\U0001F1F7", True),
    League("N1",  "Eredivisie",       "Netherlands", "\U0001F1F3\U0001F1F1", True),
    League("P1",  "Primeira Liga",    "Portugal",    "\U0001F1F5\U0001F1F9", True),
    # --- configured but inactive ---
    League("E2",  "League One",       "England",     "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F", False),
    League("E3",  "League Two",       "England",     "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F", False),
    League("EC",  "National League",  "England",     "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F", False),
    League("SC0", "Premiership",      "Scotland",    "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F", False),
    League("D2",  "2. Bundesliga",    "Germany",     "\U0001F1E9\U0001F1EA", False),
    League("I2",  "Serie B",          "Italy",       "\U0001F1EE\U0001F1F9", False),
    League("SP2", "Segunda Division", "Spain",       "\U0001F1EA\U0001F1F8", False),
    League("F2",  "Ligue 2",          "France",      "\U0001F1EB\U0001F1F7", False),
    League("B1",  "Pro League",       "Belgium",     "\U0001F1E7\U0001F1EA", False),
    League("T1",  "Super Lig",        "Turkey",      "\U0001F1F9\U0001F1F7", False),
]

BY_CODE: dict[str, League] = {lg.code: lg for lg in LEAGUES}
ACTIVE: list[League] = [lg for lg in LEAGUES if lg.active]

# Seasons pulled for fitting and backtesting, oldest first.
# football-data.co.uk season codes: "1819" == 2018/19.
SEASONS: list[str] = ["1819", "1920", "2021", "2122", "2223", "2324", "2425", "2526"]

# --- model defaults -------------------------------------------------------
# Chosen a priori from the Dixon-Coles literature, NOT tuned against backtest
# output. Do not adjust these to improve a headline number.
HALF_LIFE_DAYS = 365.0   # exponential time decay on match weights
MAX_GOALS = 10           # score matrix truncation
