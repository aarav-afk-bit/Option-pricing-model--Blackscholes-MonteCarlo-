"""Monte Carlo Lab engine: unbiased, much lower error than plain MC, reproducible."""

import numpy as np
import pytest

from montecarlo.engine import Contract, control_variate, price_gbm
from pricing import black_scholes

CASES = [
    Contract(S=100, K=100, T=0.5, r=0.06, q=0.0, option_type="call"),
    Contract(S=100, K=110, T=0.25, r=0.06, q=0.01, option_type="call"),
    Contract(S=24500, K=24000, T=30 / 365, r=0.065, q=0.0, option_type="put"),
]


@pytest.mark.parametrize("c", CASES, ids=lambda c: f"{c.option_type}-{c.K}")
def test_matches_black_scholes_within_confidence_interval(c):
    sigma = 0.22
    bs = black_scholes(c.S, c.K, c.T, c.r, sigma, c.q)["call" if c.is_call else "put"]
    mc = price_gbm(c, sigma, paths=40_000, seed=1)
    assert abs(mc["price"] - bs) < 4 * mc["stdError"]
    assert mc["ci95"][0] < mc["price"] < mc["ci95"][1]


def test_variance_reduction_beats_plain_monte_carlo():
    c = CASES[0]
    reduced = price_gbm(c, 0.2, paths=20_000, seed=3)
    # For an ATM call the control variate alone typically cuts variance 3-5x.
    assert reduced["efficiencyGain"] > 3
    plain = price_gbm(c, 0.2, paths=20_000, seed=3, use_control=False)
    assert reduced["stdError"] < plain["stdError"] / 1.5


def test_same_seed_same_answer():
    assert price_gbm(CASES[1], 0.3, seed=9) == price_gbm(CASES[1], 0.3, seed=9)


def test_put_call_parity_holds_on_shared_paths():
    c = Contract(S=100, K=95, T=1.0, r=0.05, q=0.02, option_type="call")
    p = Contract(S=100, K=95, T=1.0, r=0.05, q=0.02, option_type="put")
    call = price_gbm(c, 0.25, seed=5)["price"]
    put = price_gbm(p, 0.25, seed=5)["price"]
    assert call - put == pytest.approx(100 * np.exp(-0.02) - 95 * np.exp(-0.05), abs=0.05)


def test_control_variate_removes_known_error():
    rng = np.random.default_rng(0)
    x = rng.normal(size=5000)
    y = 2 * x + rng.normal(scale=0.1, size=5000) + 7
    adjusted, beta = control_variate(y, x, 0.0)
    assert beta == pytest.approx(2, abs=0.01)
    assert np.std(adjusted) < 0.2


def test_expired_or_zero_vol_is_intrinsic():
    assert price_gbm(Contract(110, 100, 0, 0.05), 0.2)["price"] == 10
    assert price_gbm(Contract(90, 100, 0.5, 0.05, option_type="put"), 0.0)["price"] == 10
