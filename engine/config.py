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
