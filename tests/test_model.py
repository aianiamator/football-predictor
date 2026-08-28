"""Verification of the Dixon-Coles implementation against simulated data.

Three things are checked:
  1. the analytic gradient matches a finite-difference gradient
  2. known attack/defence/home-advantage parameters are recovered from data
     simulated out of the model itself
  3. the score matrix is a proper distribution and the tau correction moves
     low scorelines in the documented direction

Run with:  python -m tests.test_model
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from scipy.special import gammaln

from engine.model import DixonColes, _objective, decay_weights


def simulate(n_teams=20, n_seasons=6, seed=7):
    """Generate matches from the Dixon-Coles model with known parameters."""
    rng = np.random.default_rng(seed)
    teams = [f"Team{i:02d}" for i in range(n_teams)]

    attack = rng.normal(0, 0.35, n_teams)
    attack -= attack.mean()          # match the identifying constraint
    defence = rng.normal(0, 0.30, n_teams)
    gamma = 0.28
    rho = -0.05

    rows = []
    start = np.datetime64("2016-08-01")
    for season in range(n_seasons):
        pairs = [(i, j) for i in range(n_teams) for j in range(n_teams) if i != j]
        rng.shuffle(pairs)
        for k, (i, j) in enumerate(pairs):
            lam = np.exp(attack[i] + defence[j] + gamma)
            mu = np.exp(attack[j] + defence[i])

            # Sample from the tau-corrected joint by rejection on the 2x2 block.
            while True:
                x = rng.poisson(lam)
                y = rng.poisson(mu)
                if x == 0 and y == 0:
                    accept = 1.0 - lam * mu * rho
                elif x == 0 and y == 1:
                    accept = 1.0 + lam * rho
                elif x == 1 and y == 0:
                    accept = 1.0 + mu * rho
                elif x == 1 and y == 1:
                    accept = 1.0 - rho
                else:
                    accept = 1.0
                if rng.random() < accept / 1.3:
                    break

            day = start + np.timedelta64(season * 300 + (k * 300) // len(pairs), "D")
            rows.append((pd.Timestamp(day), teams[i], teams[j], int(x), int(y)))

    df = pd.DataFrame(rows, columns=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    df = df.sort_values("Date").reset_index(drop=True)
    truth = {"teams": teams, "attack": attack, "defence": defence, "gamma": gamma, "rho": rho}
    return df, truth


def test_gradient():
    """Analytic gradient must match finite differences."""
    df, _ = simulate(n_teams=8, n_seasons=2, seed=3)
    teams = sorted(set(df["HomeTeam"]) | set(df["AwayTeam"]))
    n = len(teams)
    idx = {t: i for i, t in enumerate(teams)}
    hi = df["HomeTeam"].map(idx).to_numpy(int)
    ai = df["AwayTeam"].map(idx).to_numpy(int)
    hg = df["FTHG"].to_numpy(float)
    ag = df["FTAG"].to_numpy(float)
    w = decay_weights(df["Date"].to_numpy(), np.datetime64(df["Date"].max(), "D"))

    rng = np.random.default_rng(11)
    x = np.concatenate([rng.normal(0, 0.2, 2 * n - 1), [0.3], [-0.04]])

    _, grad = _objective(x, hi, ai, hg, ag, w, n)

    eps = 1e-6
    num = np.zeros_like(x)
    for k in range(len(x)):
        xp, xm = x.copy(), x.copy()
        xp[k] += eps
        xm[k] -= eps
        fp, _ = _objective(xp, hi, ai, hg, ag, w, n)
        fm, _ = _objective(xm, hi, ai, hg, ag, w, n)
        num[k] = (fp - fm) / (2 * eps)

    max_err = np.max(np.abs(grad - num))
    rel = max_err / max(1.0, np.max(np.abs(num)))
    print(f"  gradient: max abs err {max_err:.3e}, relative {rel:.3e}")
    assert rel < 1e-6, f"analytic gradient disagrees with finite differences ({rel:.2e})"
    return True


def test_recovery():
    """Fitting simulated data must recover the generating parameters."""
    df, truth = simulate(n_teams=20, n_seasons=6, seed=7)

    # Long half-life so the whole simulated history counts roughly equally;
    # this isolates estimation accuracy from the decay.
    model = DixonColes.fit(df, half_life_days=100000.0)

    order = [model.index[t] for t in truth["teams"]]
    est_attack = model.attack[order]
    est_defence = model.defence[order]
    est_defence = est_defence - est_defence.mean() + truth["defence"].mean()

    attack_corr = float(np.corrcoef(est_attack, truth["attack"])[0, 1])
    defence_corr = float(np.corrcoef(est_defence, truth["defence"])[0, 1])
    attack_rmse = float(np.sqrt(np.mean((est_attack - truth["attack"]) ** 2)))
    defence_rmse = float(np.sqrt(np.mean((est_defence - truth["defence"]) ** 2)))

    print(f"  matches simulated: {len(df)}")
    print(f"  attack  corr {attack_corr:.4f}  rmse {attack_rmse:.4f}")
    print(f"  defence corr {defence_corr:.4f}  rmse {defence_rmse:.4f}")
    print(f"  home advantage  true {truth['gamma']:.4f}  est {model.home_advantage:.4f}")
    print(f"  rho             true {truth['rho']:.4f}  est {model.rho:.4f}")

    assert model.converged, "optimiser did not converge"
    assert attack_corr > 0.95, f"attack correlation too low: {attack_corr:.3f}"
    assert defence_corr > 0.95, f"defence correlation too low: {defence_corr:.3f}"
    assert attack_rmse < 0.10, f"attack rmse too high: {attack_rmse:.3f}"
    assert abs(model.home_advantage - truth["gamma"]) < 0.05, "home advantage not recovered"
    return True


def test_distribution():
    """Score matrix must be a normalised distribution with coherent margins."""
    df, _ = simulate(n_teams=12, n_seasons=3, seed=5)
    model = DixonColes.fit(df, half_life_days=100000.0)
    home, away = model.teams[0], model.teams[1]

    m = model.score_matrix(home, away)
    assert abs(m.sum() - 1.0) < 1e-9, "score matrix does not sum to 1"
    assert (m >= 0).all(), "negative probability in score matrix"

    p = model.predict(home, away)
    total = p["home_win"] + p["draw"] + p["away_win"]
    assert abs(total - 1.0) < 1e-9, f"outcome probabilities sum to {total}"
    assert abs(p["over25"] + p["under25"] - 1.0) < 1e-9
    assert abs(p["btts"] + p["no_btts"] - 1.0) < 1e-9

    # Expected goals from the truncated matrix should track the fitted rates.
    n = m.shape[0]
    eg_home = float((m.sum(axis=1) * np.arange(n)).sum())
    lam, _ = model.rates(home, away)
    print(f"  sum(P)={m.sum():.10f}  H/D/A={p['home_win']:.3f}/{p['draw']:.3f}/{p['away_win']:.3f}")
    print(f"  matrix E[home goals]={eg_home:.4f} vs fitted lambda={lam:.4f}")
    assert abs(eg_home - lam) < 0.05, "truncation is distorting expected goals"

    # rho < 0 must lift the 0-0 cell relative to independent Poissons.
    lam_r, mu_r = model.rates(home, away)
    k = np.arange(n)
    ph = np.exp(k * np.log(lam_r) - lam_r - gammaln(k + 1.0))
    pa = np.exp(k * np.log(mu_r) - mu_r - gammaln(k + 1.0))
    indep = np.outer(ph, pa)
    indep = indep / indep.sum()
    print(f"  P(0-0) corrected={m[0, 0]:.5f} independent={indep[0, 0]:.5f} rho={model.rho:+.4f}")
    if model.rho < 0:
        assert m[0, 0] > indep[0, 0], "tau correction has the wrong sign at 0-0"
    return True


def test_rho_recovery():
    """rho is a small effect on four cells, so it needs a large sample.

    This checks the estimator is consistent, not that rho is pinned down on
    two seasons of data - on ~2000 matches its standard error is large.
    """
    df, truth = simulate(n_teams=20, n_seasons=25, seed=7)
    model = DixonColes.fit(df, half_life_days=100000.0)
    err = abs(model.rho - truth["rho"])
    print(f"  n={len(df)}  rho true {truth['rho']:+.4f}  est {model.rho:+.4f}  err {err:.4f}")
    assert err < 0.03, f"rho not recovered at large n: est {model.rho:+.4f}"
    return True


def test_decay():
    """Weights must halve over one half-life and never exceed 1."""
    ref = np.datetime64("2024-01-01")
    dates = np.array(["2024-01-01", "2023-01-02", "2022-01-02"], dtype="datetime64[D]")
    w = decay_weights(dates, ref, half_life_days=365.0)
    print(f"  weights: {np.round(w, 4)}")
    assert abs(w[0] - 1.0) < 1e-9
    assert abs(w[1] - 0.5) < 0.01
    assert abs(w[2] - 0.25) < 0.01
    return True


def main():
    tests = [
        ("time decay weights", test_decay),
        ("analytic gradient", test_gradient),
        ("score distribution", test_distribution),
        ("parameter recovery from simulated data", test_recovery),
        ("rho recovery at large n", test_rho_recovery),
    ]
    failed = 0
    for name, fn in tests:
        print(f"\n[ {name} ]")
        try:
            fn()
            print("  PASS")
        except AssertionError as exc:
            print(f"  FAIL: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{'ALL PASSED' if failed == 0 else str(failed) + ' FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
