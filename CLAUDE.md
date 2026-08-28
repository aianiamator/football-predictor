# Football forecasting system

Statistical match forecasting for Nigerian and African diaspora football fans.
Sports analytics and education. **This is not a betting product.**

## Non-negotiable product constraints

These override every other instruction in this repo.

1. **Never** use the words *bet, betting, odds, stake, tip, accumulator, banker,
   sure,* or *guaranteed* anywhere in the interface or user-facing copy.
   (`odds_home/odds_draw/odds_away` exist inside `engine/` only, as the
   bookmaker benchmark for backtesting. Never surfaced, never published.)
2. **Never** suggest anyone act on a forecast, financially or otherwise.
3. **Never** imply certainty. The strongest permitted phrasing is
   *"strong favourite"*.
4. Permanent footer on every screen:
   *"Forecasts are statistical estimates from past results. Football is
   unpredictable — even strong favourites lose."*
5. **There are no API keys anywhere in the app.** The frontend fetches static
   JSON from a CDN, so there is no service to authenticate against and nothing
   to leak. If any key or secret ever appears under `app/`, stop and report it.
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
  config.py      Model constants only (XI_PER_DAY, MAX_GOALS).
  data.py        football-data.co.uk loader + the league registry.
  model.py       Dixon-Coles. Attack/defence/home advantage, time decay, tau.
  backtest.py    Walk-forward backtest, calibration, bookmaker benchmark.
  store.py       SQLite store + atomic static-JSON publishing.
  run.py         Fits all leagues, predicts fixtures, writes store + JSON.
  settle.py      Fills in actual results on past predictions. (Phase 4)
schema.sql       SQLite schema. Applied automatically by store.connect().
output/          The static files Cloudflare serves. Generated, gitignored.
data/forecasts.db   The durable record. Generated, gitignored.
tests/           Simulated-data verification, leakage audit, store guarantees,
                 payload + product-constraint checks.
tools/dev_seed.py  DEV-ONLY data generator. Never publish its output.
scripts/         Deployment: cron job wrappers, healthcheck, deploy, n8n.
DEPLOY.md        How it runs on the Hetzner box, and how to check it is.
app/             Vite + TS + Tailwind PWA. Read-only, no keys. React is
                 aliased to preact/compat: ~20.6 KB gzipped shell.
```

Data flows one way:

    football-data.co.uk → engine → SQLite (Hetzner) → static JSON → Cloudflare → app

**The app never writes, and never authenticates.**

### Why a database AND static files

The app only ever needs ~6 KB of JSON, so a live database on the read path
would be pure overhead — the `supabase-js` client alone measured 55 KB gzipped,
nine times the payload it fetches. That is the wrong trade on metered mobile
data.

But pure JSON files cannot guarantee a forecast is never rewritten after the
fact, and the public track record is this product's entire trust asset. So
SQLite holds the durable record with that guarantee enforced by a trigger, and
the engine publishes small derived JSON files for the edge to serve.

| published file | contents |
|---|---|
| `predictions.json` | unsettled fixtures from today onward, limit 100 |
| `track-record.json` | per-league accuracy, overall, last 20 settled |
| `meta.json` | publish timestamp for the app's freshness check |

All three are written temp-then-rename, so a reader never sees a partial file.

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

`XI_PER_DAY = 0.0018` (weight = `exp(-xi * age_days)`, about a 385-day
half-life) comes from the Dixon-Coles literature. It was **not** selected by
trying values and keeping whichever produced the best backtest number. Do not
tune these against backtest output — that is exactly how a model gets fooled
into looking better than it is. `rho` is fitted by MLE.

## Leakage discipline

This is the thing most likely to silently break. At each refit point `t`:

- training data is strictly `date < t`
- the decay reference date is `t`, so no future match affects any weight
- only that matchday's fixtures are predicted
- a fixture is skipped unless the model already knows both teams

Realistic result accuracy is **low-to-mid 50s**. If a league reports above 60%,
treat it as a bug and look for leakage before believing it. `test_leakage.py`
fails the build if that ceiling is breached.

`tests/test_leakage.py` guards this three ways: a structural audit of every
refit point, a placebo run on randomly reshuffled scorelines (which must
collapse the edge to roughly zero), and a hard plausibility ceiling.

## Canonical data schema

One lowercase schema everywhere downstream of `data.py`:

    league  date  home_team  away_team  home_goals  away_goals
    odds_home  odds_draw  odds_away  season

`odds_*` exist **only** as the bookmaker benchmark inside the backtest. They are
never published, never written to the store, never shown to a user.

## What the numbers say about the product

Measured in the first full run (see `RESULTS.md`):

- **BTTS has no signal** — +0.71pp over its majority-class baseline, with a
  Brier score *worse* than baseline. The backtest prints its own instruction:
  do not present this market. This conflicts with the Phase 3 detail screen.
- **Draws are almost never the argmax** — 106 predicted vs 5,117 actual out of
  20,231. Never reduce a forecast to a single predicted outcome; the three-way
  bar is the honest representation.
- **The top of the confidence scale is overstated** — the 90-100% band lands at
  81.7%. Reserve "strong favourite" for a band where it actually holds.

Every accuracy figure must be published next to its baseline. The edge is the
number, never the raw accuracy.

## Commands

```bash
python -m tests.test_model      # verify the model against simulated data
python -m tests.test_leakage    # structural + placebo leakage audit
python -m tests.test_store      # forecast immutability + publish guarantees
python -m tests.test_payload    # payload shape + product-constraint checks
python -m engine.backtest       # full walk-forward backtest (~3 min, 7 leagues)
python -m engine.run            # fit, predict fixtures, publish
python -m engine.settle         # fill in results on past predictions

python -m tests.test_settle     # settle job against real results
python -m tools.dev_seed        # DEV data for the app (never publish it)
./scripts/healthcheck.sh        # is it actually running? exits non-zero if not
npm install --prefix app
npm run dev --prefix app        # http://localhost:5178
npm run build --prefix app      # VITE_DATA_URL=<cdn> to point at Cloudflare
```

Raw CSVs cache under `data_cache/`, so re-runs do not re-download.

## The app

See `app/README.md`. Three things worth knowing before touching it:

1. **`ThreeWayBar.tsx` is the product.** A reader must be able to take in the
   whole forecast from its shape before reading a word. Colours are the darker
   green/slate/blue rather than the brightest, because white bold text on bright
   green fails contrast on a cheap LCD in daylight.
2. **Grey means exactly one thing per screen.** The draw segment is a cool
   slate, so low confidence is a warm stone. Do not let them converge.
3. **Translation never parses English.** The engine publishes `summary_key` +
   `summary_args`; the app looks up a template. Adding a language touches only
   `src/i18n.ts`.

## Operations

Scheduled on the Hetzner box (see `DEPLOY.md`):

- `scripts/run_predictions.sh` daily at 05:30 — forecasts
- `scripts/run_settle.sh` every 6 hours — results, which make the record real
- `scripts/healthcheck.sh` daily — exits non-zero when something has stopped

Both jobs take a `flock`, so a slow run can never be overtaken by the next one
and corrupt the database.

Two failure modes worth knowing:

1. **The silent stall.** Jobs exit 0, publish nothing, and the site keeps
   serving last week's forecasts looking entirely normal. `publish freshness`
   in the healthcheck is what catches it.
2. **Zero upcoming forecasts is usually NOT a fault.** football-data publishes
   fixtures only days before each round, so between rounds the feed is
   legitimately empty and the engine correctly refuses to forecast matches
   already played. Check the feed before debugging the engine.

`npm run build` refuses to run while `app/public/data/` exists, so dev data
with invented fixtures can never be shipped as real forecasts.

## Secrets

There are no API keys in this project. The engine reads a public CSV feed and
writes to a local SQLite file; the app reads static JSON from a CDN. `.env` is
gitignored and only ever holds non-secret config such as `FORECAST_DB`.

If a key ever becomes necessary, it stays server-side. Nothing under `app/`
may contain a secret of any kind.

## Measured results

First-run figures are recorded in `RESULTS.md`. They are honest walk-forward
numbers, not a target to be improved by fiddling with settings.
