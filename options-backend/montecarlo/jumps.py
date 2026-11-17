"""
Merton jump-diffusion model.

Black-Scholes prices only smooth, continuous moves. Real prices also gap -
results, budget day, global shocks. Merton adds jumps on top of the usual
diffusion:

    dS/S = (r - q - lam*k) dt + sigma dW + (J - 1) dN

* lam       - expected number of jumps per year (dN is a Poisson process)
* jump_mean - average log size of a jump (negative = crashes more likely than spikes)
* jump_vol  - spread of jump sizes
* k = E[J] - 1 compensates the drift so the model stays arbitrage-free.

Jumps fatten both tails, so far-from-the-money options are worth more than
Black-Scholes says - especially short-dated ones, where smooth diffusion
barely moves the price. The terminal distribution is simulated exactly
(no time stepping), and merton_price() gives the closed-form series
solution as a check.
"""

import math
from dataclasses import asdict, dataclass

import numpy as np

from montecarlo.engine import antithetic_normals, make_rng, path_fan, price_terminal
from pricing import black_scholes


@dataclass(frozen=True)
class JumpParams:
    lam: float = 1.0          # jumps per year
    jump_mean: float = -0.05  # mean log jump size
    jump_vol: float = 0.08    # std of log jump size

    @property
    def k(self):
        return math.exp(self.jump_mean + 0.5 * self.jump_vol ** 2) - 1

    def as_dict(self):
        return asdict(self)


def simulate_terminal(contract, sigma, p, n_pairs, rng):
    """Exact draw of S_T: Poisson jump count, normal jump sizes, antithetic diffusion and jumps."""
    T = contract.T
    counts = rng.poisson(p.lam * T, n_pairs)
    counts = np.concatenate([counts, counts])
    z = antithetic_normals(rng, n_pairs)
    zj = antithetic_normals(rng, n_pairs)
    jump_sum = counts * p.jump_mean + np.sqrt(counts) * p.jump_vol * zj
    drift = (contract.r - contract.q - p.lam * p.k - 0.5 * sigma ** 2) * T
    return contract.S * np.exp(drift + sigma * np.sqrt(T) * z + jump_sum)


def price_merton_mc(contract, sigma, p, paths=50_000, seed=None):
    n_pairs = max(paths // 2, 2)
    ST = simulate_terminal(contract, sigma, p, n_pairs, make_rng(seed))
    return price_terminal(contract, ST, n_pairs)


def merton_price(contract, sigma, p, terms=60):
    """Merton's closed form: a Poisson-weighted sum of Black-Scholes prices."""
    T, lam_prime = contract.T, p.lam * (1 + p.k)
    total, weight = 0.0, math.exp(-lam_prime * T)
    for n in range(terms):
        if n:
            weight *= lam_prime * T / n
        sigma_n = math.sqrt(sigma ** 2 + n * p.jump_vol ** 2 / T)
        r_n = contract.r - p.lam * p.k + n * math.log(1 + p.k) / T
        bs = black_scholes(contract.S, contract.K, T, r_n, sigma_n, contract.q)
        # Weight by lam' = lam(1+k): the jump-adjusted Poisson probabilities make each
        # Black-Scholes term (at its own r_n and sigma_n) correctly discounted already.
        total += weight * (bs["call"] if contract.is_call else bs["put"])
        if n > lam_prime * T and weight < 1e-14:
            break
    return float(total)


def merton_fan(contract, sigma, p, paths=4_000, steps=60, seed=None):
    rng = make_rng(None if seed is None else seed + 1)
    n_pairs = max(paths // 2, 2)
    dt = contract.T / steps
    counts = rng.poisson(p.lam * dt, (n_pairs, steps))
    counts = np.concatenate([counts, counts])
    z = antithetic_normals(rng, n_pairs, (steps,))
    zj = antithetic_normals(rng, n_pairs, (steps,))
    increments = ((contract.r - contract.q - p.lam * p.k - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z
                  + counts * p.jump_mean + np.sqrt(counts) * p.jump_vol * zj)
    log_paths = np.concatenate([np.zeros((2 * n_pairs, 1)), np.cumsum(increments, axis=1)], axis=1)
    return path_fan(contract, contract.S * np.exp(log_paths))
