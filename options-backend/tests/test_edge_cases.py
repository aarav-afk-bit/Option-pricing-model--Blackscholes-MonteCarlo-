"""Degenerate inputs (at expiry, zero volatility) must give finite, sensible values."""

import math
import warnings

import pytest

from pricing import black_scholes, crr_price, greeks, implied_volatility, monte_carlo

GREEK_KEYS = {"callDelta", "putDelta", "gamma", "vega", "callTheta", "putTheta",
              "callRho", "putRho", "vanna", "vomma", "callCharm", "putCharm"}


@pytest.fixture(autouse=True)
def no_numpy_warnings():
    # Divide-by-zero used to surface as RuntimeWarnings and NaN/inf in the JSON.
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        yield


@pytest.mark.parametrize("T, sigma", [(0.0, 0.2), (-0.01, 0.2), (0.5, 0.0), (0.0, 0.0)])
@pytest.mark.parametrize("S", [90.0, 100.0, 110.0])
def test_all_outputs_are_finite(S, T, sigma):
    K, r, q = 100.0, 0.06, 0.01
    values = list(greeks(S, K, T, r, sigma, q).values())
    values += [black_scholes(S, K, T, r, sigma, q)[k] for k in ("call", "put")]
    values += [crr_price(S, K, T, r, sigma, q, 50, side, american)
               for side in ("call", "put") for american in (True, False)]
    values += list(monte_carlo(S, K, T, r, sigma, q, 2000))
    assert all(math.isfinite(v) for v in values)
    assert set(greeks(S, K, T, r, sigma, q)) == GREEK_KEYS


def test_expired_option_is_intrinsic():
    assert black_scholes(110, 100, 0, 0.05, 0.2) == {"call": 10.0, "put": 0.0, "d1": None, "d2": None}
    assert crr_price(90, 100, 0, 0.05, 0.2, option_type="put") == 10.0


@pytest.mark.parametrize("S, call_delta, put_delta", [(110, 1.0, 0.0), (90, 0.0, -1.0), (100, 0.5, -0.5)])
def test_delta_at_expiry(S, call_delta, put_delta):
    g = greeks(S, 100, 0, 0.05, 0.2)
    assert (g["callDelta"], g["putDelta"]) == (call_delta, put_delta)
    assert g["gamma"] == g["vega"] == 0.0


def test_zero_vol_price_is_discounted_forward():
    S, K, T, r = 100.0, 95.0, 0.5, 0.06
    expected = S - K * math.exp(-r * T)
    assert black_scholes(S, K, T, r, 0.0)["call"] == pytest.approx(expected)
    assert black_scholes(S, K, T, r, 0.0)["put"] == 0.0


@pytest.mark.parametrize("side", ["call", "put"])
def test_limits_match_formulas_near_the_edge(side):
    # Deep in the money with tiny time left, the closed-form Greeks approach the limits.
    S = 120.0 if side == "call" else 80.0
    near = greeks(S, 100.0, 1e-6, 0.06, 0.2, 0.01)
    at = greeks(S, 100.0, 0.0, 0.06, 0.2, 0.01)
    for key in (f"{side}Delta", f"{side}Theta", "gamma", "vega"):
        assert near[key] == pytest.approx(at[key], abs=1e-3)


def test_implied_volatility_is_undefined_at_expiry():
    assert implied_volatility(5.0, 100, 100, 0, 0.05) is None
