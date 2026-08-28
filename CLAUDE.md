# Football forecasting system

Statistical match forecasting for Nigerian and African diaspora football fans.
Sports analytics and education. **This is not a betting product.**

## Non-negotiable product constraints

These override every other instruction in this repo.

1. **Never** use the words *bet, betting, odds, stake, tip, accumulator, banker,
   sure,* or *guaranteed* anywhere in the interface or user-facing copy.
   (`OddsH/OddsD/OddsA` exist inside `engine/` only, as the bookmaker benchmark
   for backtesting. They are never surfaced to a user and never published.)
2. **Never** suggest anyone act on a forecast, financially or otherwise.
3. **Never** imply certainty. The strongest permitted phrasing is
   *"strong favourite"*.
4. Permanent footer on every screen:
   *"Forecasts are statistical estimates from past results. Football is
   unpredictable — even strong favourites lose."*
5. The **service-role key is server-side only**. If it ever appears anywhere
   under `app/`, stop and report it immediately. The app uses the anon key only.
6. The track record screen is **never hidden or filtered**. Misses must show as
   prominently as hits.

## Audience constraints

Cheap Android phones, slow and expensive mobile data, some users with limited
English literacy. This drives the design rule: **every screen must be
understandable with the text removed.** Meaning comes from colour, size, shape
and position first; words only confirm it.

- Never a number without a visual equivalent beside it
- Minimum body text 18px, minimum tap target 56px
- No dropdowns, no modals, no hamburger menu, no horizontal scrolling
- Maximum two taps to reach anything
- Never write *probability*, *expected goals*, *model*, or *algorithm* in the UI

## Architecture

```
engine/          Python. Fits models, predicts, publishes. Server-side only.
  config.py      18 leagues configured, 8 active. Model constants.
  data.py        Downloads + normalises football-data.co.uk. No API key needed.
  model.py       Dixon-Coles. Attack/defence/home advantage, time decay, tau.
  backtest.py    Walk-forward backtest, calibration, bookmaker benchmark.
  run.py         Fits all leagues, predicts fixtures, writes JSON + Supabase.
  settle.py      Fills in actual results on past predictions. (Phase 4)
tests/           Verification against simulated data + leakage audit.
app/             React + Vite + TS + Tailwind PWA. Read-only, anon key only.
supabase_schema.sql
```

Data flows one way: `football-data.co.uk` → `engine` → Supabase → `app`.
**The app never writes.**

## The model

Dixon-Coles. For home team *i* against away team *j*:

```
log lambda = attack_i + defence_j + gamma     (home goals)
log mu     = attack_j + defence_i             (away goals)
```

`defence` is a conceding rate — higher means weaker. `attack` is constrained to
sum to zero for identifiability. The joint scoreline mass is two Poissons times
the Dixon-Coles `tau` correction, which fixes the known misfit on 0-0, 0-1, 1-0
and 1-1. Fitted by weighted MLE with exponential time decay, using an analytic
gradient (without it the walk-forward backtest is impractically slow).

### Parameters are chosen a priori, not tuned

`HALF_LIFE_DAYS = 365` comes from the Dixon-Coles literature. It was **not**
selected by trying values and keeping whichever produced the best backtest
number. Do not tune these against backtest output — that is exactly how a
model gets fooled into looking better than it is. `rho` is fitted by MLE.

## Leakage discipline

This is the thing most likely to silently break. At each refit point `t`:

- training data is strictly `Date < t`
- the decay reference date is `t`, so no future match affects any weight
- predictions cover only `t <= Date < t + REFIT_DAYS`
- a fixture is skipped unless both teams have `>= MIN_TEAM_MATCHES` history

Realistic result accuracy is **low-to-mid 50s**. If a league reports above 60%,
treat it as a bug and look for leakage before believing it.

`tests/test_leakage.py` guards this two ways: a structural audit of every refit
window, and a placebo run on randomly reshuffled results — which must collapse
the edge to roughly zero.

## Commands

```bash
python -m tests.test_model      # verify the model against simulated data
python -m tests.test_leakage    # structural + placebo leakage audit
python -m engine.backtest       # full walk-forward backtest (~2 min, 8 leagues)
python -m engine.backtest E0    # one league
python -m engine.run            # fit, predict fixtures, publish
python -m engine.settle         # fill in results on past predictions
```

Raw CSVs cache under `data/raw/`, so re-runs do not re-download.

## Secrets

`.env` is gitignored and holds `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.
Never paste a key into chat, a commit, or anything under `app/`.
The app reads only `VITE_`-prefixed vars and only ever the anon key.

## Measured results

First-run figures are recorded in `RESULTS.md`. They are honest walk-forward
numbers, not a target to be improved by fiddling with settings.
