"""
Dixon-Coles bivariate-Poisson football model.

Fits per-team attack/defence strengths + home advantage + low-score correction (rho),
with exponential time-decay weighting. Produces a full scoreline probability matrix from
which every goals-based market is derived.

Reference: Dixon & Coles (1997), "Modelling Association Football Scores".
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10


@dataclass
class DCParams:
    teams: list[str]
    attack: dict[str, float]
    defence: dict[str, float]
    home_adv: float
    rho: float


def _tau(h, a, lam, mu, rho):
    """Dixon-Coles low-score correction factor."""
    if h == 0 and a == 0:
        return 1.0 - lam * mu * rho
    if h == 0 and a == 1:
        return 1.0 + lam * rho
    if h == 1 and a == 0:
        return 1.0 + mu * rho
    if h == 1 and a == 1:
        return 1.0 - rho
    return 1.0


def _time_weights(dates: pd.Series, ref_date: pd.Timestamp, xi: float) -> np.ndarray:
    """exp(-xi * age_in_days). xi small => slow decay."""
    age_days = (ref_date - pd.to_datetime(dates)).dt.days.clip(lower=0).to_numpy()
    return np.exp(-xi * age_days)


def fit(matches: pd.DataFrame, ref_date: pd.Timestamp, xi: float = 0.0018) -> DCParams:
    """
    Fit Dixon-Coles on a matches DataFrame with columns:
    date, home_team, away_team, fthg, ftag.
    """
    teams = sorted(set(matches["home_team"]) | set(matches["away_team"]))
    n = len(teams)
    idx = {t: i for i, t in enumerate(teams)}

    h_idx = matches["home_team"].map(idx).to_numpy()
    a_idx = matches["away_team"].map(idx).to_numpy()
    hg = matches["fthg"].to_numpy(dtype=float)
    ag = matches["ftag"].to_numpy(dtype=float)
    w = _time_weights(matches["date"], ref_date, xi)

    # params: [attack(n), defence(n), home_adv, rho]
    init = np.concatenate([np.zeros(n), np.zeros(n), [0.25], [-0.05]])

    def negloglik(params):
        attack = params[:n]
        defence = params[n:2 * n]
        home_adv = params[2 * n]
        rho = params[2 * n + 1]

        lam = np.exp(home_adv + attack[h_idx] - defence[a_idx])
        mu = np.exp(attack[a_idx] - defence[h_idx])

        ll = (poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu))

        # DC correction (vectorised over the 4 low-score cells)
        tau = np.ones_like(lam)
        m00 = (hg == 0) & (ag == 0)
        m01 = (hg == 0) & (ag == 1)
        m10 = (hg == 1) & (ag == 0)
        m11 = (hg == 1) & (ag == 1)
        tau[m00] = 1.0 - lam[m00] * mu[m00] * rho
        tau[m01] = 1.0 + lam[m01] * rho
        tau[m10] = 1.0 + mu[m10] * rho
        tau[m11] = 1.0 - rho
        tau = np.clip(tau, 1e-9, None)

        ll = ll + np.log(tau)
        return -np.sum(w * ll)

    # constraint: mean attack = 0 (identifiability)
    cons = [{"type": "eq", "fun": lambda p: np.sum(p[:n])}]
    bounds = [(-3, 3)] * (2 * n) + [(-1, 2), (-0.2, 0.2)]

    res = minimize(negloglik, init, method="SLSQP", bounds=bounds,
                   constraints=cons, options={"maxiter": 200, "ftol": 1e-6})

    p = res.x
    return DCParams(
        teams=teams,
        attack={t: p[idx[t]] for t in teams},
        defence={t: p[n + idx[t]] for t in teams},
        home_adv=float(p[2 * n]),
        rho=float(p[2 * n + 1]),
    )


def score_matrix(params: DCParams, home: str, away: str, max_goals: int = MAX_GOALS) -> np.ndarray | None:
    """Probability matrix M[h, a] = P(home scores h, away scores a). None if team unseen."""
    if home not in params.attack or away not in params.attack:
        return None
    lam = np.exp(params.home_adv + params.attack[home] - params.defence[away])
    mu = np.exp(params.attack[away] - params.defence[home])

    h_probs = poisson.pmf(np.arange(max_goals + 1), lam)
    a_probs = poisson.pmf(np.arange(max_goals + 1), mu)
    M = np.outer(h_probs, a_probs)

    # apply DC correction to the 4 low-score cells
    M[0, 0] *= 1.0 - lam * mu * params.rho
    M[0, 1] *= 1.0 + lam * params.rho
    M[1, 0] *= 1.0 + mu * params.rho
    M[1, 1] *= 1.0 - params.rho

    M = np.clip(M, 0, None)
    M /= M.sum()
    return M


# ---- market derivations from the scoreline matrix ----

def m_1x2(M):
    home = np.tril(M, -1).sum()      # h > a
    draw = np.trace(M)               # h == a
    away = np.triu(M, 1).sum()       # a > h
    return {"H": home, "D": draw, "A": away}


def m_double_chance(M):
    p = m_1x2(M)
    return {"1X": p["H"] + p["D"], "12": p["H"] + p["A"], "X2": p["D"] + p["A"]}


def m_over_under(M, line: float):
    n = M.shape[0]
    total = np.add.outer(np.arange(n), np.arange(n))
    over = M[total > line].sum()
    return {"Over": float(over), "Under": float(1.0 - over)}


def m_btts(M):
    no = M[0, :].sum() + M[:, 0].sum() - M[0, 0]
    return {"Yes": float(1.0 - no), "No": float(no)}


def m_correct_score(M, top: int = 8):
    n = M.shape[0]
    scores = [((h, a), float(M[h, a])) for h in range(n) for a in range(n)]
    scores.sort(key=lambda x: x[1], reverse=True)
    return {f"{h}-{a}": p for (h, a), p in scores[:top]}
