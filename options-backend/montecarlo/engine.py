"""
Core Monte Carlo machinery shared by every model in the lab.

Plain Monte Carlo needs ~4x the paths to halve its error. Two standard
variance-reduction techniques make each path count for much more:

* Antithetic variates - every draw Z is paired with -Z, so their errors
  partly cancel.
* Control variate - the discounted terminal stock price has a known mean,
  S*e^(-qT). Whatever error the simulation makes on it is used to correct the
  option estimate, scaled by how strongly the two move together.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Contract:
    S: float              # spot
    K: float              # strike
    T: float              # years to expiry
    r: float              # risk-free rate (decimal)
    q: float = 0.0        # dividend yield (decimal)
    option_type: str = "call"

    @property
    def is_call(self):
        return self.option_type.lower() == "call"

    @property
    def discount(self):
        return float(np.exp(-self.r * self.T))


def payoff(ST, K, is_call):
    return np.maximum(ST - K, 0.0) if is_call else np.maximum(K - ST, 0.0)


def make_rng(seed=None):
    return np.random.default_rng(seed)


def antithetic_normals(rng, n_pairs, shape=()):
    """2*n_pairs standard normals as [Z, -Z] stacked on the first axis."""
    z = rng.standard_normal((n_pairs, *shape))
    return np.concatenate([z, -z], axis=0)


def summarize(samples, paths, plain_samples=None):
    """
    Price, standard error and 95% interval from i.i.d. discounted samples.

    `paths` is the number of simulated paths behind the samples (antithetic
    pairs count as two). If `plain_samples` - the same paths without variance
    reduction - is given, also report how many times fewer paths the reduced
    estimator needs for the same accuracy.
    """
    n = len(samples)
    price = float(np.mean(samples))
    se = float(np.std(samples, ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    out = {
        "price": price,
        "stdError": se,
        "ci95": [price - 1.96 * se, price + 1.96 * se],
        "paths": int(paths),
    }
    if plain_samples is not None and se > 0:
        plain_se = float(np.std(plain_samples, ddof=1) / np.sqrt(len(plain_samples)))
        out["efficiencyGain"] = (plain_se / se) ** 2
    return out


def control_variate(y, x, x_mean):
    """
    Adjust samples y using a control x with known expectation x_mean:
    y - beta * (x - x_mean), beta = cov(y, x) / var(x).
    """
    var_x = np.var(x, ddof=1)
    if var_x <= 0:
        return y, 0.0
    beta = np.cov(y, x, ddof=1)[0, 1] / var_x
    return y - beta * (x - x_mean), float(beta)


def price_terminal(contract, ST, n_pairs, use_control=True):
    """
    Price a European option from antithetic terminal prices ST (length
    2*n_pairs, first half Z and second half -Z). Pair averages are the i.i.d.
    samples; the discounted terminal price is the control variate.
    """
    disc = contract.discount
    y_all = disc * payoff(ST, contract.K, contract.is_call)
    x_all = disc * ST
    y = 0.5 * (y_all[:n_pairs] + y_all[n_pairs:])
    x = 0.5 * (x_all[:n_pairs] + x_all[n_pairs:])
    beta = 0.0
    if use_control:
        expected_x = contract.S * np.exp(-contract.q * contract.T)
        y, beta = control_variate(y, x, expected_x)
    result = summarize(y, 2 * n_pairs, plain_samples=y_all)
    result["controlBeta"] = beta
    return result


def gbm_terminal(contract, sigma, n_pairs, rng):
    """Terminal prices under geometric Brownian motion (the Black-Scholes world)."""
    z = antithetic_normals(rng, n_pairs)
    drift = (contract.r - contract.q - 0.5 * sigma ** 2) * contract.T
    return contract.S * np.exp(drift + sigma * np.sqrt(contract.T) * z)


def price_gbm(contract, sigma, paths=50_000, seed=None, use_control=True):
    """
    European price under GBM with antithetic + control-variate reduction.
    Should match Black-Scholes within its confidence interval - the lab
    uses this as the sanity check before trusting the richer models.
    """
    if contract.T <= 0 or sigma <= 0:
        value = max(contract.S - contract.K, 0.0) if contract.is_call else max(contract.K - contract.S, 0.0)
        return {"price": float(value), "stdError": 0.0, "ci95": [float(value)] * 2, "paths": 0, "controlBeta": 0.0}
    n_pairs = max(paths // 2, 2)
    ST = gbm_terminal(contract, sigma, n_pairs, make_rng(seed))
    return price_terminal(contract, ST, n_pairs, use_control)


def gbm_convergence(contract, sigma, paths=50_000, seed=None, points=12):
    """
    How the price estimate settles as paths are added, for plain Monte Carlo
    and for the variance-reduced estimator, computed on the same random
    draws. Checkpoints are spaced geometrically from 500 paths to `paths`.
    """
    if contract.T <= 0 or sigma <= 0:
        return []
    n_pairs = max(paths // 2, 2)
    ST = gbm_terminal(contract, sigma, n_pairs, make_rng(seed))
    disc = contract.discount
    y_all = disc * payoff(ST, contract.K, contract.is_call)
    # Interleave each draw with its antithetic partner so any prefix holds whole pairs.
    plain = np.empty(2 * n_pairs)
    plain[0::2], plain[1::2] = y_all[:n_pairs], y_all[n_pairs:]

    checkpoints = np.unique(np.geomspace(min(250, n_pairs), n_pairs, points).astype(int))
    series = []
    for k in checkpoints:
        sub = np.concatenate([ST[:k], ST[n_pairs:n_pairs + k]])
        reduced = price_terminal(contract, sub, k)
        plain_part = summarize(plain[:2 * k], 2 * k)
        series.append({
            "paths": int(2 * k),
            "plain": {"price": plain_part["price"], "stdError": plain_part["stdError"]},
            "reduced": {"price": reduced["price"], "stdError": reduced["stdError"]},
        })
    return series


def gbm_paths(contract, sigma, n_pairs, steps, rng):
    """Full price paths under GBM: array of shape (2*n_pairs, steps+1), column 0 = spot."""
    dt = contract.T / steps
    z = antithetic_normals(rng, n_pairs, (steps,))
    increments = (contract.r - contract.q - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z
    log_paths = np.concatenate([np.zeros((2 * n_pairs, 1)), np.cumsum(increments, axis=1)], axis=1)
    return contract.S * np.exp(log_paths)


def path_fan(contract, paths, samples=24):
    """
    Summary of simulated price paths for plotting: percentile bands at each
    time step, a few example paths, and how many paths finish in the money.
    """
    steps = paths.shape[1] - 1
    days = np.linspace(0.0, contract.T * 365, steps + 1)
    bands = {f"p{p}": np.percentile(paths, p, axis=0).round(2).tolist() for p in (5, 25, 50, 75, 95)}
    pick = np.linspace(0, paths.shape[0] // 2 - 1, samples).astype(int)  # spread across the non-mirrored half
    final = paths[:, -1]
    itm = final > contract.K if contract.is_call else final < contract.K
    return {
        "days": days.round(3).tolist(),
        **bands,
        "samples": paths[pick].round(2).tolist(),
        "finalItmShare": float(np.mean(itm)),
    }


def gbm_fan(contract, sigma, paths=4_000, steps=60, seed=None):
    if contract.T <= 0 or sigma <= 0:
        return None
    rng = make_rng(None if seed is None else seed + 1)
    return path_fan(contract, gbm_paths(contract, sigma, max(paths // 2, 2), steps, rng))
