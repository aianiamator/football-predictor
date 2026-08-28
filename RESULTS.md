# Backtest results — first run

**First-run figures from newly written code, not a reproduction of a previously
verified result.** Nothing has been tuned against them.

- Run date: 2026-08-28
- Seasons: 2018/19 → 2025/26 (8 per league)
- 20,231 out-of-sample predictions across 8 leagues
- Settings: refit every 7 days, `min_train_matches=400`, `xi=0.0018/day`
  (~385-day half-life), full history in each training window
- Runtime: 2m50s

## Headline

| Metric | Model | Baseline / benchmark | Edge |
|---|---:|---:|---:|
| Result accuracy | 51.25% | 43.16% always-home | **+8.09pp** |
| Log loss | 1.0000 | 0.9774 bookmaker | **−0.0226 (worse)** |
| Bookmaker accuracy | — | 52.86% | **−1.61pp (worse)** |
| Over/under 2.5 | 56.56% | 52.10% majority class | **+4.45pp** |
| Both teams score | 54.01% | 53.29% majority class | **+0.71pp** |

Measured bookmaker overround: 5.25%. Odds coverage 20,230 of 20,231.

## Per league

| League | N | 1X2 acc | Home base | Edge | Book acc | vs book | Log loss | Book LL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Primeira Liga | 2,036 | 54.47% | 42.78% | +11.69pp | 56.58% | −2.11pp | 0.9511 | 0.9245 |
| Eredivisie | 1,967 | 53.89% | 44.43% | +9.46pp | 55.67% | −1.78pp | 0.9629 | 0.9398 |
| Serie A | 2,625 | 53.14% | 40.53% | +12.61pp | 54.12% | −0.95pp | 0.9865 | 0.9659 |
| Premier League | 2,632 | 52.62% | 43.35% | +9.27pp | 54.45% | −1.82pp | 0.9897 | 0.9687 |
| La Liga | 2,632 | 52.43% | 45.29% | +7.14pp | 53.80% | −1.37pp | 0.9894 | 0.9708 |
| Ligue 1 | 2,305 | 51.15% | 42.91% | +8.24pp | 52.49% | −1.34pp | 1.0085 | 0.9866 |
| Bundesliga | 2,038 | 50.88% | 43.18% | +7.70pp | 52.80% | −1.91pp | 1.0031 | 0.9747 |
| Championship | 3,996 | 45.62% | 43.04% | +2.58pp | 47.32% | −1.70pp | 1.0594 | 1.0366 |

## Over/under and BTTS, against their majority-class baselines

| League | O/U acc | O/U base | O/U edge | O/U Brier | base Brier | BTTS acc | BTTS base | BTTS edge | BTTS Brier | base Brier |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Primeira Liga | 55.70% | 50.44% | +5.26pp | 0.2492 | 0.2500 | 51.72% | 51.13% | +0.59pp | 0.2549 | 0.2499 |
| La Liga | 57.75% | 53.19% | +4.56pp | 0.2445 | 0.2490 | 53.65% | 51.63% | +2.01pp | 0.2507 | 0.2497 |
| Serie A | 55.16% | 51.89% | +3.28pp | 0.2485 | 0.2496 | 54.70% | 54.06% | +0.65pp | 0.2498 | 0.2484 |
| Ligue 1 | 55.36% | 52.84% | +2.52pp | 0.2493 | 0.2492 | 52.62% | 54.19% | **−1.56pp** | 0.2530 | 0.2482 |
| Premier League | 57.22% | 55.02% | +2.20pp | 0.2468 | 0.2475 | 53.88% | 53.88% | **0.00pp** | 0.2501 | 0.2485 |
| Championship | 54.03% | 52.93% | +1.10pp | 0.2517 | 0.2491 | 51.88% | 50.63% | +1.25pp | 0.2526 | 0.2500 |
| Eredivisie | 58.87% | 58.46% | +0.41pp | 0.2403 | 0.2428 | 56.33% | 56.02% | +0.31pp | 0.2477 | 0.2464 |
| Bundesliga | 60.89% | 60.89% | **0.00pp** | 0.2348 | 0.2381 | 59.52% | 59.72% | **−0.20pp** | 0.2399 | 0.2406 |

## Calibration (pooled; each match contributes its H, D and A forecast)

| Band | Predicted | Observed | N |
|---|---:|---:|---:|
| 0–10% | 6.8% | 9.0% | 2,111 |
| 10–20% | 15.9% | 16.3% | 8,015 |
| 20–30% | 25.4% | 26.3% | 23,204 |
| 30–40% | 34.4% | 33.8% | 10,479 |
| 40–50% | 44.7% | 43.5% | 7,124 |
| 50–60% | 54.6% | 52.7% | 4,705 |
| 60–70% | 64.4% | 65.3% | 2,796 |
| 70–80% | 74.4% | 72.0% | 1,537 |
| 80–90% | 83.8% | 79.9% | 607 |
| 90–100% | 92.9% | 81.7% | 115 |

## Three findings that affect the product

### 1. BTTS has no signal. Do not present it.

Pooled edge +0.71pp, and the Brier score is **worse** than the baseline
(0.2502 vs 0.2489) — the forecasts are anti-informative as probabilities.
Premier League edge is exactly 0.00pp, Ligue 1 is −1.56pp, Bundesliga −0.20pp.
The backtest prints its own warning: *"BTTS edge is under 2pp. Do not present
this market."* This conflicts with the Phase 3 spec, which puts a both-teams-
score element on the match detail screen.

### 2. The model almost never names a draw.

**106 draws predicted out of 20,231 matches (0.5%). 5,117 actually occurred
(25.3%).** This is a known Dixon-Coles property, not a bug — a draw is rarely
the single most likely outcome even when it is common. The consequence is that
any single "predicted result" label is a home-or-away label roughly always,
while a quarter of matches end level. The three-way bar shows this honestly;
a one-word verdict would not.

### 3. Confidence is overstated at the top end.

The three highest calibration bands all run overconfident: 74.4%→72.0%,
83.8%→79.9%, 92.9%→81.7%. The 90–100% band is 11pp over on 115 samples. Given
the constraint that the product must never imply certainty, "strong favourite"
should be reserved for a band where the claim actually holds, and the top of
the scale should not be presented as near-certain.

Over/under 2.5 does survive (+4.45pp pooled, Brier better than baseline), but
it is weakest exactly where the base rate is already high — Bundesliga +0.00pp,
Eredivisie +0.41pp.

## Verification

`tests/test_model.py` — analytic gradient matches finite differences to 5.0e-10
relative error; attack/defence recovered from simulated data at r=0.97/0.95;
home advantage 0.269 vs 0.280 true; rho within 0.021 at n=9,500. rho is weakly
identified below ~5,000 matches, which is expected — it adjusts four cells.

`tests/test_leakage.py` — 233 refit points audited, training strictly precedes
every matchday. Placebo run on reshuffled scorelines drops the edge from +9.3pp
to −2.5pp. A plausibility test fails the build if accuracy exceeds 60%.

## Caveats

- The test window includes the closed-stadium COVID period, when home advantage
  was unusually weak. Real data, left in.
- O/U and BTTS baselines are computed from the test set's own base rate, which
  makes them slightly harder to beat than a genuinely prospective baseline.
  That is conservative in the right direction.
- Fixtures involving a team the model has never seen are skipped, not counted
  as misses.
