"""Model constants.

The league registry lives in engine/data.py (LEAGUES, CORE_LEAGUES) so there is
exactly one source of truth for which leagues exist and which are published.
"""

# Chosen a priori from the Dixon-Coles literature, NOT tuned against backtest
# output. Do not adjust these to improve a headline number.
#
# XI_PER_DAY is the exponential time-decay rate on match weights:
#     weight = exp(-XI_PER_DAY * age_in_days)
# 0.0018/day is a half-life of about 385 days - roughly one season.
XI_PER_DAY = 0.0018

# Score matrix truncation. Beyond 10 goals the mass is negligible.
MAX_GOALS = 10

# L2 penalty on attack and defence ratings - a Gaussian prior centred on
# "average team". Set to 0.0 to reproduce the original unpenalised fit.
# The value is selected by chronological out-of-sample validation in
# tools/tune_ridge.py, on matches strictly EARLIER than the reported test
# period, and must never be tuned against the test set.
RIDGE = 2.0


# --- prediction engine version -------------------------------------------
# Stamped onto every forecast at the moment it is made, and never rewritten.
# Old forecasts keep the version that produced them, so v1 and v2 can be
# compared fairly instead of history being silently re-scored by new code.
# Bump this whenever the model's OUTPUT would change for the same inputs.
MODEL_VERSION = "1.1.0"   # 1.0.0 = unpenalised; 1.1.0 = ridge-regularised

# --- confidence bands -----------------------------------------------------
# Based on the top probability. These are provisional: the thresholds were set
# from observed calibration, not validated as decision rules, so the app must
# not present them as scientifically established. Adjust here, nowhere else.
#
# (label, minimum top probability)
CONFIDENCE_BANDS = [
    ("high", 0.70),
    ("strong", 0.60),
    ("moderate", 0.50),
    ("low", 0.0),
]

# --- edge bands -----------------------------------------------------------
# Margin between the top two outcomes, in percentage points. Two forecasts with
# the same top probability are NOT equally decisive: 41/27/32 is a coin toss
# with a favourite, 41/18/41 is a genuine tie. The margin says which.
#
# (label, minimum margin in points)
MARGIN_BANDS = [
    ("clear_edge", 20.0),
    ("reasonable_edge", 10.0),
    ("small_edge", 5.0),
    ("too_close", 0.0),
]

# A margin at or below this is treated as no meaningful separation at all.
TIE_MARGIN_POINTS = 1.0
