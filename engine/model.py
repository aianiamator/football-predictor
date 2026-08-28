"""Dixon-Coles bivariate Poisson-style model for football scorelines.

Per-team attack and defence ratings plus a shared home advantage, fitted by
weighted maximum likelihood with exponential time decay and the Dixon-Coles
low-score correction.

Goal rates for home team i against away team j:

    log lambda = attack_i + defence_j + gamma      (home goals)
    log mu     = attack_j + defence_i              (away goals)

defence is a conceding rate: higher means a weaker defence. attack is
constrained to sum to zero, which makes the parameterisation identified.

The joint mass is the product of two Poissons multiplied by the Dixon-Coles
correction tau, which reallocates probability among the four lowest scorelines
where independent Poissons are known to misfit:

    tau(0,0) = 1 - lambda*mu*rho     tau(0,1) = 1 + lambda*rho
    tau(1,0) = 1 + mu*rho            tau(1,1) = 1 - rho

An analytic gradient is supplied; without it the numerical gradient over
2n+1 parameters makes the walk-forward backtest impractically slow.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from .config import MAX_GOALS, XI_PER_DAY

TAU_FLOOR = 1e-10
RHO_BOUND = 0.2


def decay_weights(match_dates, reference_date, xi: float = XI_PER_DAY) -> np.ndarray:
    """Exponential time-decay weights: weight = exp(-xi * age_in_days).

    1.0 at the reference date, falling as matches get older. xi=0 disables
    decay entirely, which is useful for testing against simulated data.
    """
    age_days = (np.asarray(reference_date, dtype="datetime64[D]")
                - np.asarray(match_dates, dtype="datetime64[D]")).astype(float)
    age_days = np.maximum(age_days, 0.0)
    return np.exp(-xi * age_days)


def _unpack(params: np.ndarray, n: int):
    attack_free = params[: n - 1]
    attack = np.concatenate([attack_free, [-attack_free.sum()]])
    defence = params[n - 1 : 2 * n - 1]
    gamma = params[2 * n - 1]
    rho = params[2 * n]
    return attack, defence, gamma, rho


def _objective(params, hi, ai, hg, ag, w, n):
    """Weighted negative log-likelihood and its analytic gradient."""
    attack, defence, gamma, rho = _unpack(params, n)

    log_lam = attack[hi] + defence[ai] + gamma
    log_mu = attack[ai] + defence[hi]
    lam = np.exp(log_lam)
    mu = np.exp(log_mu)

    ll = (hg * log_lam - lam - gammaln(hg + 1.0)
          + ag * log_mu - mu - gammaln(ag + 1.0))

    # Dixon-Coles low-score correction.
    m00 = (hg == 0) & (ag == 0)
    m01 = (hg == 0) & (ag == 1)
    m10 = (hg == 1) & (ag == 0)
    m11 = (hg == 1) & (ag == 1)

    tau = np.ones_like(lam)
    tau[m00] = 1.0 - lam[m00] * mu[m00] * rho
    tau[m01] = 1.0 + lam[m01] * rho
    tau[m10] = 1.0 + mu[m10] * rho
    tau[m11] = 1.0 - rho
    tau = np.maximum(tau, TAU_FLOOR)
    ll = ll + np.log(tau)

    neg_ll = -np.sum(w * ll)

    # --- gradient ---------------------------------------------------------
    dt_dloglam = np.zeros_like(lam)
    dt_dlogmu = np.zeros_like(lam)
    dt_drho = np.zeros_like(lam)

    inv = 1.0 / tau
    dt_dloglam[m00] = inv[m00] * (-lam[m00] * mu[m00] * rho)
    dt_dlogmu[m00] = inv[m00] * (-lam[m00] * mu[m00] * rho)
    dt_drho[m00] = inv[m00] * (-lam[m00] * mu[m00])

    dt_dloglam[m01] = inv[m01] * (lam[m01] * rho)
    dt_drho[m01] = inv[m01] * lam[m01]

    dt_dlogmu[m10] = inv[m10] * (mu[m10] * rho)
    dt_drho[m10] = inv[m10] * mu[m10]

    dt_drho[m11] = inv[m11] * (-1.0)

    g_loglam = w * (hg - lam + dt_dloglam)   # dLL/d(log lambda) per match
    g_logmu = w * (ag - mu + dt_dlogmu)      # dLL/d(log mu) per match

    d_attack = (np.bincount(hi, weights=g_loglam, minlength=n)
                + np.bincount(ai, weights=g_logmu, minlength=n))
    d_defence = (np.bincount(ai, weights=g_loglam, minlength=n)
                 + np.bincount(hi, weights=g_logmu, minlength=n))
    d_gamma = g_loglam.sum()
    d_rho = np.sum(w * dt_drho)

    # attack[n-1] = -sum(attack_free), so chain through the constraint.
    d_attack_free = d_attack[: n - 1] - d_attack[n - 1]

    grad = np.concatenate([d_attack_free, d_defence, [d_gamma], [d_rho]])
    return neg_ll, -grad


class DixonColes:
    """Fitted ratings for a single league."""

    def __init__(self, teams, attack, defence, home_advantage, rho,
                 n_matches=0, reference_date=None, converged=True, league=None):
        self.teams = list(teams)
        self.index = {t: i for i, t in enumerate(self.teams)}
        self.attack = np.asarray(attack, dtype=float)
        self.defence = np.asarray(defence, dtype=float)
        self.home_advantage = float(home_advantage)
        self.rho = float(rho)
        self.n_matches = int(n_matches)
        self.reference_date = reference_date
        self.converged = bool(converged)
        self.league = league

    # -- fitting -----------------------------------------------------------
    @classmethod
    def fit(cls, df, reference_date=None, xi: float = XI_PER_DAY,
            init: "DixonColes | None" = None, maxiter: int = 400,
            league: str | None = None) -> "DixonColes":
        """Fit to a results frame with home_team/away_team/home_goals/away_goals/date.

        reference_date anchors the time decay. It must be the moment of
        prediction, never a date after any match used for training.
        """
        if reference_date is None:
            reference_date = df["date"].max()

        teams = sorted(set(df["home_team"]) | set(df["away_team"]))
        n = len(teams)
        if n < 2 or len(df) < n:
            raise ValueError(f"not enough data to fit: {len(df)} matches, {n} teams")

        idx = {t: i for i, t in enumerate(teams)}
        hi = df["home_team"].map(idx).to_numpy(dtype=int)
        ai = df["away_team"].map(idx).to_numpy(dtype=int)
        hg = df["home_goals"].to_numpy(dtype=float)
        ag = df["away_goals"].to_numpy(dtype=float)
        w = decay_weights(df["date"].to_numpy(), np.datetime64(reference_date, "D"), xi)

        x0 = np.zeros(2 * n + 1)
        x0[2 * n - 1] = 0.25   # a mild positive home advantage
        x0[2 * n] = -0.03      # rho is typically slightly negative
        if init is not None:
            prev_attack = np.array([init.attack[init.index[t]] if t in init.index else 0.0 for t in teams])
            prev_attack -= prev_attack.mean()
            prev_defence = np.array([init.defence[init.index[t]] if t in init.index else 0.0 for t in teams])
            x0[: n - 1] = prev_attack[: n - 1]
            x0[n - 1 : 2 * n - 1] = prev_defence
            x0[2 * n - 1] = init.home_advantage
            x0[2 * n] = init.rho

        bounds = ([(-3.0, 3.0)] * (n - 1) + [(-3.0, 3.0)] * n
                  + [(-1.0, 1.0), (-RHO_BOUND, RHO_BOUND)])

        res = minimize(_objective, x0, args=(hi, ai, hg, ag, w, n), jac=True,
                       method="L-BFGS-B", bounds=bounds,
                       options={"maxiter": maxiter, "ftol": 1e-10, "gtol": 1e-7})

        attack, defence, gamma, rho = _unpack(res.x, n)
        return cls(teams, attack, defence, gamma, rho,
                   n_matches=len(df), reference_date=reference_date,
                   converged=bool(res.success), league=league)

    # -- prediction --------------------------------------------------------
    def knows(self, team: str) -> bool:
        return team in self.index

    def rates(self, home: str, away: str) -> tuple[float, float]:
        h, a = self.index[home], self.index[away]
        lam = float(np.exp(self.attack[h] + self.defence[a] + self.home_advantage))
        mu = float(np.exp(self.attack[a] + self.defence[h]))
        return lam, mu

    def score_matrix(self, home: str, away: str, max_goals: int = MAX_GOALS) -> np.ndarray:
        """Joint distribution over scorelines, rows = home goals."""
        lam, mu = self.rates(home, away)
        k = np.arange(max_goals + 1)
        m = np.outer(np.exp(k * np.log(lam) - lam - gammaln(k + 1.0)),
                     np.exp(k * np.log(mu) - mu - gammaln(k + 1.0)))

        m[0, 0] *= 1.0 - lam * mu * self.rho
        m[0, 1] *= 1.0 + lam * self.rho
        m[1, 0] *= 1.0 + mu * self.rho
        m[1, 1] *= 1.0 - self.rho

        m = np.maximum(m, 0.0)
        total = m.sum()
        if total <= 0:
            raise ValueError("degenerate score matrix")
        return m / total

    def predict(self, home: str, away: str, max_goals: int = MAX_GOALS) -> dict:
        """Full forecast for one fixture."""
        m = self.score_matrix(home, away, max_goals)
        n = m.shape[0]
        gh = np.arange(n)[:, None]
        ga = np.arange(n)[None, :]

        home_win = float(m[gh > ga].sum())
        draw = float(np.trace(m))
        away_win = float(m[gh < ga].sum())

        over25 = float(m[(gh + ga) >= 3].sum())
        btts = float(m[1:, 1:].sum())

        lam, mu = self.rates(home, away)

        flat_idx = np.argsort(m.reshape(-1))[::-1][:5]
        probs = m.reshape(-1)
        scorelines = [
            {"home": int(i // n), "away": int(i % n), "prob": float(probs[i])}
            for i in flat_idx
        ]

        return {
            "home_win": home_win,
            "draw": draw,
            "away_win": away_win,
            "over_2_5": over25,
            "under_2_5": 1.0 - over25,
            "both_teams_score": btts,
            "no_both_teams_score": 1.0 - btts,
            "exp_home_goals": lam,
            "exp_away_goals": mu,
            "likely_score": {"home": scorelines[0]["home"], "away": scorelines[0]["away"]},
            "likely_scorelines": scorelines,
        }


def fit(df, xi: float = XI_PER_DAY, league: str | None = None,
        reference_date=None, init: "DixonColes | None" = None) -> DixonColes:
    """Module-level entry point. Fit one league's ratings.

    Raises ValueError when there is not enough data to identify the ratings,
    which callers are expected to catch and skip.
    """
    return DixonColes.fit(df, reference_date=reference_date, xi=xi,
                          init=init, league=league)
