"""
Heston stochastic-volatility model.

Black-Scholes freezes volatility. In Heston the variance v_t itself moves:

    dS/S = (r - q) dt + sqrt(v) dW1
    dv   = kappa (theta - v) dt + xi sqrt(v) dW2,     corr(dW1, dW2) = rho

* kappa - how fast variance is pulled back to its long-run level theta
* theta - long-run variance (theta = vol^2)
* xi    - "vol of vol": how much the variance itself fluctuates
* rho   - usually negative for equities: volatility rises when prices fall,
          which fattens the downside tail and makes OTM puts dearer than
          Black-Scholes says - the skew seen in real NSE option chains.

Prices come from Monte Carlo (Andersen's QE scheme, antithetic draws and the
discounted-price control variate). heston_price_cf() is Heston's
semi-analytic formula, used to verify the simulation and, later, to calibrate
the parameters to market prices quickly.
"""

import math
from dataclasses import asdict, dataclass

import numpy as np

from montecarlo.engine import Contract, antithetic_normals, make_rng, path_fan, price_terminal


@dataclass(frozen=True)
class HestonParams:
    v0: float          # current variance
    kappa: float       # mean-reversion speed
    theta: float       # long-run variance
    xi: float          # volatility of variance
    rho: float         # correlation between price and variance shocks

    @classmethod
    def from_vol(cls, sigma, kappa=2.0, xi=0.4, rho=-0.6):
        """Defaults centred on today's volatility: v0 = theta = sigma^2."""
        return cls(v0=sigma ** 2, kappa=kappa, theta=sigma ** 2, xi=xi, rho=rho)

    def as_dict(self):
        d = asdict(self)
        d["vol0"], d["volLongRun"] = float(np.sqrt(self.v0)), float(np.sqrt(self.theta))
        return d


def simulate(contract, p, n_pairs, steps, rng, keep_paths=False):
    """
    Terminal prices (and optionally full paths) under Heston using Andersen's
    Quadratic-Exponential (QE) scheme. Plain Euler steps let the variance go
    negative and bias prices by ~1% at daily steps when vol-of-vol is high;
    QE samples the variance from a distribution matched to its true mean and
    variance over each step, so it stays accurate with few steps. Draws are
    antithetic (Z with -Z, U with 1-U).
    """
    dt = contract.T / steps
    n = 2 * n_pairs
    zv = antithetic_normals(rng, n_pairs, (steps,))
    zs = antithetic_normals(rng, n_pairs, (steps,))
    u_half = rng.random((n_pairs, steps))
    uv = np.concatenate([u_half, 1.0 - u_half], axis=0)

    e = np.exp(-p.kappa * dt)
    c1 = p.xi ** 2 * e * (1 - e) / p.kappa
    c2 = p.theta * p.xi ** 2 * (1 - e) ** 2 / (2 * p.kappa)
    # Log-price step coefficients (Andersen 2008, central discretisation gamma1 = gamma2 = 1/2).
    k0 = -p.rho * p.kappa * p.theta * dt / p.xi
    k1 = 0.5 * dt * (p.kappa * p.rho / p.xi - 0.5) - p.rho / p.xi
    k2 = 0.5 * dt * (p.kappa * p.rho / p.xi - 0.5) + p.rho / p.xi
    k3 = 0.5 * dt * (1 - p.rho ** 2)

    log_s = np.full(n, np.log(contract.S))
    v = np.full(n, p.v0)
    paths = np.empty((n, steps + 1)) if keep_paths else None
    if keep_paths:
        paths[:, 0] = contract.S
    for t in range(steps):
        m = p.theta + (v - p.theta) * e
        s2 = v * c1 + c2
        psi = s2 / np.maximum(m * m, 1e-300)
        quad_branch = psi <= 1.5
        # Quadratic branch: v' = a (b + Z)^2, for moderate dispersion.
        inv = 2 / np.where(quad_branch, psi, 1.0)
        b2 = np.maximum(inv - 1 + np.sqrt(inv) * np.sqrt(np.maximum(inv - 1, 0)), 0)
        v_quad = m / (1 + b2) * (np.sqrt(b2) + zv[:, t]) ** 2
        # Exponential branch: a point mass at zero plus an exponential tail.
        pz = (psi - 1) / (psi + 1)
        beta = (1 - pz) / np.maximum(m, 1e-300)
        ratio = np.maximum((1 - pz) / np.maximum(1 - uv[:, t], 1e-300), 1.0)
        v_exp = np.where(uv[:, t] <= pz, 0.0, np.log(ratio) / beta)
        v_next = np.where(quad_branch, v_quad, v_exp)

        log_s += ((contract.r - contract.q) * dt + k0 + k1 * v + k2 * v_next
                  + np.sqrt(np.maximum(k3 * (v + v_next), 0)) * zs[:, t])
        v = v_next
        if keep_paths:
            paths[:, t + 1] = np.exp(log_s)
    return np.exp(log_s), paths


def steps_for(contract):
    """About one step per trading day, between 20 and 120."""
    return int(np.clip(round(contract.T * 252), 20, 120))


def price_heston_mc(contract, p, paths=50_000, seed=None):
    n_pairs = max(paths // 2, 2)
    ST, _ = simulate(contract, p, n_pairs, steps_for(contract), make_rng(seed))
    return price_terminal(contract, ST, n_pairs)


def heston_fan(contract, p, paths=4_000, seed=None):
    rng = make_rng(None if seed is None else seed + 1)
    _, matrix = simulate(contract, p, max(paths // 2, 2), 60, rng, keep_paths=True)
    return path_fan(contract, matrix)


def _char_fn(u, contract, p):
    """Characteristic function of ln S_T (Albrecher et al. 'little trap' form, numerically stable)."""
    iu = 1j * u
    b = p.kappa - p.rho * p.xi * iu
    d = np.sqrt(b ** 2 + p.xi ** 2 * (iu + u ** 2))
    g = (b - d) / (b + d)
    edt = np.exp(-d * contract.T)
    C = (contract.r - contract.q) * iu * contract.T + p.kappa * p.theta / p.xi ** 2 * (
        (b - d) * contract.T - 2 * np.log((1 - g * edt) / (1 - g)))
    D = (b - d) / p.xi ** 2 * (1 - edt) / (1 - g * edt)
    return np.exp(C + D * p.v0 + iu * np.log(contract.S))


_GL_X, _GL_W = np.polynomial.legendre.leggauss(256)


def _integration_limit(T, p):
    """
    Upper limit for the Fourier integral. The integrand decays like
    exp(-v T u^2 / 2) for small u but only exponentially, with rate about
    (v0 + kappa theta T) sqrt(1 - rho^2) / xi, further out when vol-of-vol is
    high - so take whichever needs the longer range.
    """
    v_min = max(min(p.v0, p.theta), 1e-4)
    gaussian = 12 / math.sqrt(v_min * T)
    exponential = 35 * p.xi / max((p.v0 + p.kappa * p.theta * T) * math.sqrt(max(1 - p.rho ** 2, 1e-4)), 1e-6)
    return float(np.clip(max(gaussian, exponential), 50, 5000))


def heston_prices(S, K, T, r, q, p, is_call):
    """
    Semi-analytic Heston prices for an array of strikes at once by Fourier
    inversion with Gauss-Legendre quadrature (the characteristic function is
    shared by every strike, so a whole chain costs about a millisecond).
    """
    K = np.atleast_1d(np.asarray(K, dtype=float))
    c = Contract(S=S, K=1.0, T=T, r=r, q=q)
    umax = _integration_limit(T, p)
    u = 0.5 * umax * (_GL_X + 1)
    w = 0.5 * umax * _GL_W
    forward = S * math.exp((r - q) * T)
    phi2 = _char_fn(u, c, p)
    phi1 = _char_fn(u - 1j, c, p) / forward
    phase = np.exp(-1j * np.outer(np.log(K), u))
    P1 = 0.5 + (phase * phi1 / (1j * u)).real @ w / math.pi
    P2 = 0.5 + (phase * phi2 / (1j * u)).real @ w / math.pi
    call = S * math.exp(-q * T) * P1 - K * math.exp(-r * T) * P2
    put = call - S * math.exp(-q * T) + K * math.exp(-r * T)
    return np.maximum(np.where(is_call, call, put), 0.0)


def heston_price_cf(contract, p):
    """Semi-analytic Heston price for one contract."""
    return float(heston_prices(contract.S, contract.K, contract.T, contract.r, contract.q, p, contract.is_call)[0])
