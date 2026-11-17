"""
American (early-exercise) pricing by Longstaff-Schwartz least-squares Monte Carlo.

An American option can be exercised on any day, so at each step the holder
compares "exercise now" with "keep holding". The value of holding is not
known in a simulation, so Longstaff-Schwartz estimates it by regressing the
discounted future cash flow of in-the-money paths on simple functions of
today's price, then exercises wherever immediate payoff beats that estimate.

NSE stock and index options are European; this shows what the right to
exercise early would be worth (mostly relevant for deep in-the-money puts)
and cross-checks the CRR binomial tree's American price.
"""

import numpy as np

from montecarlo.engine import gbm_paths, make_rng, payoff, summarize


def _basis(x):
    """Regression features in moneyness x = S/K: 1, x, x^2, x^3."""
    return np.column_stack([np.ones_like(x), x, x * x, x * x * x])


def price_american_lsm(contract, sigma, paths=50_000, steps=50, seed=None):
    """
    American price, its standard error, and the European price on the same
    paths, so their difference (the early-exercise premium) has little noise.
    """
    if contract.T <= 0 or sigma <= 0:
        value = float(payoff(np.array([contract.S]), contract.K, contract.is_call)[0])
        return {"price": value, "stdError": 0.0, "ci95": [value, value], "paths": 0,
                "europeanPrice": value, "earlyExercisePremium": 0.0, "exerciseShare": 0.0}

    n_pairs = max(paths // 2, 2)
    S = gbm_paths(contract, sigma, n_pairs, steps, make_rng(seed))
    dt = contract.T / steps
    step_disc = np.exp(-contract.r * dt)
    K = contract.K

    cash = payoff(S[:, -1], K, contract.is_call)   # cash flow if held to expiry
    exercise_time = np.full(S.shape[0], steps)
    for t in range(steps - 1, 0, -1):
        cash *= step_disc                          # value of future cash flow, as of step t
        intrinsic = payoff(S[:, t], K, contract.is_call)
        itm = intrinsic > 0
        if itm.sum() < 10:
            continue
        x = S[itm, t] / K
        coef, *_ = np.linalg.lstsq(_basis(x), cash[itm], rcond=None)
        continuation = _basis(x) @ coef
        ex = np.zeros_like(itm)
        ex[itm] = intrinsic[itm] > continuation
        cash[ex] = intrinsic[ex]
        exercise_time[ex] = t
    cash *= step_disc                              # back to today

    # Pair averages are i.i.d.; never exercise worth less than exercising today.
    pairs = 0.5 * (cash[:n_pairs] + cash[n_pairs:])
    result = summarize(pairs, 2 * n_pairs)
    today = float(payoff(np.array([contract.S]), K, contract.is_call)[0])
    if today > result["price"]:
        result.update(price=today, ci95=[today, today])

    euro = contract.discount * payoff(S[:, -1], K, contract.is_call)
    result["europeanPrice"] = float(np.mean(euro))
    result["earlyExercisePremium"] = max(result["price"] - result["europeanPrice"], 0.0)
    result["exerciseShare"] = float(np.mean(exercise_time < steps))
    return result
