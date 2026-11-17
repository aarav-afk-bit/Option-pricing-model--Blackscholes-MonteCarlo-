"""Heston model: formula and simulation agree, and it reduces to Black-Scholes."""

import pytest

from montecarlo.engine import Contract
from montecarlo.heston import HestonParams, heston_fan, heston_price_cf, price_heston_mc
from pricing import black_scholes


def test_tiny_vol_of_vol_reduces_to_black_scholes():
    c = Contract(S=100, K=105, T=0.5, r=0.05, q=0.01, option_type="call")
    p = HestonParams(v0=0.04, kappa=1.5, theta=0.04, xi=1e-4, rho=0.0)
    assert heston_price_cf(c, p) == pytest.approx(black_scholes(100, 105, 0.5, 0.05, 0.2, 0.01)["call"], abs=1e-4)


@pytest.mark.parametrize("option_type, K", [("call", 100), ("put", 90), ("call", 115)])
def test_simulation_matches_semi_analytic_price(option_type, K):
    c = Contract(S=100, K=K, T=0.5, r=0.05, q=0.0, option_type=option_type)
    p = HestonParams(v0=0.04, kappa=2.0, theta=0.05, xi=0.5, rho=-0.7)
    exact = heston_price_cf(c, p)
    mc = price_heston_mc(c, p, paths=80_000, seed=4)
    # Euler discretisation adds a small bias on top of the statistical error.
    assert abs(mc["price"] - exact) < 4 * mc["stdError"] + 0.004 * exact


def test_put_call_parity_in_closed_form():
    call = heston_price_cf(Contract(100, 95, 1.0, 0.05, 0.02, "call"), HestonParams.from_vol(0.25))
    put = heston_price_cf(Contract(100, 95, 1.0, 0.05, 0.02, "put"), HestonParams.from_vol(0.25))
    import math
    assert call - put == pytest.approx(100 * math.exp(-0.02) - 95 * math.exp(-0.05), abs=1e-6)


def test_negative_rho_makes_downside_puts_dearer_than_black_scholes():
    # The skew Black-Scholes cannot produce: OTM puts priced above BS at the same ATM vol.
    c = Contract(S=100, K=85, T=0.5, r=0.05, q=0.0, option_type="put")
    heston = heston_price_cf(c, HestonParams.from_vol(0.2, xi=0.6, rho=-0.8))
    bs = black_scholes(100, 85, 0.5, 0.05, 0.2)["put"]
    assert heston > 1.2 * bs


def test_qe_scheme_stays_accurate_with_extreme_vol_of_vol():
    # Feller condition badly violated (2*kappa*theta << xi^2): variance keeps hitting zero.
    # Plain Euler at ~daily steps is off by ~7 standard errors here; QE stays within noise.
    c = Contract(S=24512.35, K=24500, T=70 / 365, r=0.065, option_type="call")
    p = HestonParams.from_vol(0.13, xi=0.9, rho=-0.9)
    mc = price_heston_mc(c, p, paths=100_000, seed=11)
    assert abs(mc["price"] - heston_price_cf(c, p)) < 3 * mc["stdError"] + 0.002 * mc["price"]


def test_fan_starts_at_spot():
    c = Contract(S=100, K=100, T=0.25, r=0.05)
    fan = heston_fan(c, HestonParams.from_vol(0.3), paths=2000, seed=1)
    assert fan["p50"][0] == 100 and len(fan["samples"]) == 24


def _reference_price(c, p):
    """Slow, very precise Fourier integral (adaptive quadrature to u = 5000)."""
    import numpy as np
    from scipy.integrate import quad

    from montecarlo.heston import _char_fn
    fwd = c.S * np.exp((c.r - c.q) * c.T)
    lk = np.log(c.K)

    def g1(u):
        return (np.exp(-1j * u * lk) * _char_fn(u - 1j, c, p) / (1j * u * fwd)).real

    def g2(u):
        return (np.exp(-1j * u * lk) * _char_fn(u, c, p) / (1j * u)).real

    P1 = 0.5 + quad(g1, 1e-10, 5000, limit=5000, epsabs=1e-12)[0] / np.pi
    P2 = 0.5 + quad(g2, 1e-10, 5000, limit=5000, epsabs=1e-12)[0] / np.pi
    call = c.S * np.exp(-c.q * c.T) * P1 - c.K * np.exp(-c.r * c.T) * P2
    return call if c.is_call else call - c.S * np.exp(-c.q * c.T) + c.K * np.exp(-c.r * c.T)


@pytest.mark.parametrize("days", [7, 70, 365])
@pytest.mark.parametrize("K", [22000, 24500, 27000])
@pytest.mark.parametrize("xi, rho", [(0.3, -0.5), (0.9, -0.9)])
def test_fast_formula_matches_precise_integral(days, K, xi, rho):
    # Short expiries need a long integration range, high vol-of-vol a longer one still.
    S = 24512.35
    c = Contract(S=S, K=K, T=days / 365, r=0.065, option_type="call" if K >= S else "put")
    p = HestonParams.from_vol(0.15, xi=xi, rho=rho)
    assert heston_price_cf(c, p) == pytest.approx(max(_reference_price(c, p), 0.0), abs=1e-3)
