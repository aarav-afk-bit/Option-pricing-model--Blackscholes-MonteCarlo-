"""Calibration: models fitted to a chain reproduce it; Black-Scholes cannot fit a smile."""

import time

import numpy as np
import pytest

from montecarlo.calibrate import bs_prices, calibrate, merton_prices, select_quotes
from montecarlo.heston import HestonParams, heston_prices
from montecarlo.jumps import JumpParams

S, T, R = 24512.35, 30 / 365, 0.065
STRIKES = np.arange(22500, 26600, 250, dtype=float)
CALLS = STRIKES >= S


def quotes_from(prices):
    return [{"strike": float(k), "type": "call" if c else "put", "market": float(p)}
            for k, c, p in zip(STRIKES, CALLS, prices, strict=True) if p >= 0.5]


def test_recovers_a_heston_market_and_beats_black_scholes():
    true = HestonParams(v0=0.16 ** 2, theta=0.16 ** 2, kappa=2.0, xi=0.8, rho=-0.75)
    result = calibrate(quotes_from(heston_prices(S, STRIKES, T, R, 0.0, true, CALLS)), S, T, R)
    fits = result["fits"]
    assert result["best"] == "heston"
    assert fits["heston"]["rmseVolPts"] < 0.05                    # essentially exact
    assert fits["blackScholes"]["rmseVolPts"] > 10 * fits["heston"]["rmseVolPts"]
    assert fits["heston"]["params"]["rho"] == pytest.approx(-0.75, abs=0.05)
    assert fits["heston"]["params"]["xi"] == pytest.approx(0.8, abs=0.08)
    assert fits["heston"]["params"]["vol0"] == pytest.approx(0.16, abs=0.005)


def test_noisy_quotes_give_sensible_parameters():
    # Real last-traded prices are stale or rounded; +-4% noise must not push the fit to its limits.
    true = HestonParams(v0=0.15 ** 2, theta=0.15 ** 2, kappa=2.0, xi=0.6, rho=-0.6)
    rng = np.random.default_rng(0)
    noisy = heston_prices(S, STRIKES, T, R, 0.0, true, CALLS) * rng.uniform(0.96, 1.04, len(STRIKES))
    result = calibrate(quotes_from(noisy), S, T, R)
    h = result["fits"]["heston"]["params"]
    assert 0.12 < h["vol0"] < 0.18 and -0.9 < h["rho"] < -0.3 and 0.2 < h["xi"] < 1.5
    j = result["fits"]["jumps"]["params"]
    assert j["lam"] < 12 and 0.01 < j["jump_vol"] < 0.4


def test_recovers_a_jump_market():
    prices = merton_prices(S, STRIKES, T, R, 0.0, 0.11, JumpParams(lam=3, jump_mean=-0.06, jump_vol=0.08), CALLS)
    fits = calibrate(quotes_from(prices), S, T, R)["fits"]
    assert fits["jumps"]["rmseVolPts"] < 0.1
    assert fits["jumps"]["rmseVolPts"] < fits["blackScholes"]["rmseVolPts"] / 5


def test_flat_market_is_fitted_by_black_scholes():
    prices = bs_prices(S, STRIKES, T, R, 0.0, 0.14, CALLS)
    fits = calibrate(quotes_from(prices), S, T, R)["fits"]
    assert fits["blackScholes"]["params"]["vol"] == pytest.approx(0.14, abs=1e-4)
    assert fits["blackScholes"]["rmseVolPts"] < 0.01


def test_calibration_is_fast_enough_for_a_button_click():
    true = HestonParams(v0=0.02, theta=0.02, kappa=2.0, xi=0.6, rho=-0.6)
    quotes = quotes_from(heston_prices(S, STRIKES, T, R, 0.0, true, CALLS))
    started = time.perf_counter()
    calibrate(quotes, S, T, R)
    assert time.perf_counter() - started < 5


def test_needs_enough_quotes():
    few = quotes_from(bs_prices(S, STRIKES, T, R, 0.0, 0.14, CALLS))[:3]
    with pytest.raises(ValueError, match="at least 5"):
        calibrate(few, S, T, R)


def test_select_quotes_uses_out_of_the_money_mids_and_drops_junk():
    rows = [
        {"strikePrice": 24000, "CE": {"lastPrice": 600}, "PE": {"bidprice": 99, "askPrice": 101, "lastPrice": 90}},
        {"strikePrice": 25000, "CE": {"bidprice": 0, "askPrice": 0, "lastPrice": 80}, "PE": {"lastPrice": 560}},
        {"strikePrice": 26000, "CE": {"bidprice": 1, "askPrice": 3, "lastPrice": 2}},      # spread too wide
        {"strikePrice": 27000, "CE": {"lastPrice": 0.2}},                                  # too cheap
    ]
    assert select_quotes(rows, S) == [
        {"strike": 24000.0, "type": "put", "market": 100.0},
        {"strike": 25000.0, "type": "call", "market": 80.0},
    ]
