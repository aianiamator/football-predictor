# Backtest results — first run

**These are first-run figures from newly written code, not a reproduction of a
previously verified result.** Nothing has been tuned against them.

- Run date: 2026-08-28
- Seasons loaded: 2018/19 → 2025/26 (8 per league)
- Test period: Sept 2020 → May 2026 (the first two seasons form the initial
  training window and are never predicted)
- 17,289 out-of-sample predictions across 8 leagues
- Settings: refit every 7 days, 4-year training window, 365-day half-life,
  minimum 6 matches of history per team
- Total runtime: 2.0 minutes

## Per-league

| League | N | Result acc | Always-home | Edge | O/U 2.5 | BTTS | Log loss | Book acc | Book LL | vs book |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Primeira Liga | 1,788 | 55.3% | 43.0% | +12.3pp | 56.5% | 52.5% | 0.935 | 57.0% | 0.918 | −1.7pp |
| Eredivisie | 1,794 | 53.7% | 43.4% | +10.3pp | 58.5% | 56.0% | 0.957 | 55.5% | 0.939 | −1.8pp |
| Serie A | 2,217 | 53.1% | 40.4% | +12.7pp | 55.1% | 53.9% | 0.984 | 53.7% | 0.968 | −0.5pp |
| Premier League | 2,237 | 52.9% | 43.2% | +9.7pp | 57.2% | 54.0% | 0.986 | 54.9% | 0.966 | −2.0pp |
| La Liga | 2,242 | 52.6% | 45.1% | +7.5pp | 57.5% | 52.9% | 0.986 | 54.1% | 0.970 | −1.5pp |
| Bundesliga | 1,786 | 51.2% | 43.6% | +7.6pp | 61.7% | 59.7% | 1.000 | 52.6% | 0.980 | −1.5pp |
| Ligue 1 | 2,009 | 50.9% | 42.2% | +8.8pp | 55.5% | 53.3% | 1.008 | 52.5% | 0.986 | −1.5pp |
| Championship | 3,216 | 46.1% | 43.2% | +2.9pp | 54.4% | 52.6% | 1.054 | 47.0% | 1.038 | −0.9pp |
| **All leagues** | **17,289** | **51.5%** | **43.0%** | **+8.5pp** | **56.8%** | **54.2%** | **0.994** | **52.9%** | **0.976** | **−1.4pp** |

Odds coverage is ~100%, so the bookmaker comparison uses effectively the full
sample rather than a subset.

## Calibration (pooled; each match contributes its H, D and A forecast)

| Predicted band | N | Mean predicted | Observed | Gap |
|---|---:|---:|---:|---:|
| 0.0–0.1 | 1,746 | 7.0% | 7.7% | +0.7pp |
| 0.1–0.2 | 6,925 | 15.9% | 16.2% | +0.3pp |
| 0.2–0.3 | 19,874 | 25.4% | 26.3% | +0.8pp |
| 0.3–0.4 | 8,903 | 34.4% | 33.9% | −0.5pp |
| 0.4–0.5 | 6,037 | 44.7% | 43.4% | −1.4pp |
| 0.5–0.6 | 4,053 | 54.6% | 52.9% | −1.7pp |
| 0.6–0.7 | 2,405 | 64.5% | 65.4% | +0.9pp |
| 0.7–0.8 | 1,344 | 74.4% | 73.3% | −1.1pp |
| 0.8–0.9 | 510 | 83.8% | 82.4% | −1.4pp |
| 0.9–1.0 | 70 | 92.5% | 88.6% | −3.9pp |

Draws were 25.4% of settled matches (4,384 of 17,289).

## Verification

`tests/test_model.py` — analytic gradient matches finite differences to 3.8e-10
relative error; attack/defence recovered from simulated data at r=0.97/0.95;
home advantage recovered 0.269 vs 0.280 true; rho recovered to within 0.021 at
n=9,500. rho is weakly identified below ~5,000 matches, which is expected: it
adjusts only four scoreline cells.

`tests/test_leakage.py` — 243 refit windows audited, training strictly precedes
prediction in every one. Placebo run on randomly reshuffled results drops the
edge from +9.7pp to −2.3pp, which is what a clean pipeline should do.

## Known caveats

- The test window opens in Sept 2020, so it includes the closed-stadium COVID
  period when home advantage was unusually weak. That is real data and has been
  left in, but it depresses early home-advantage estimates.
- 429 fixtures (2.4%) were skipped because a newly promoted team had too little
  history. Skips are excluded from accuracy rather than counted as misses.
- Over/under and BTTS accuracy are scored at a 0.5 threshold, so they partly
  reflect how often the majority class occurs, not only forecast skill.
