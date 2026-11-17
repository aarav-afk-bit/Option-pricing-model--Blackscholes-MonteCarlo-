"""Merton jump-diffusion: simulation matches the closed form, and jumps fatten the tails."""

import math

import pytest

from montecarlo.engine import Contract
from montecarlo.jumps import JumpParams, merton_fan, merton_price, price_merton_mc
from pricing import black_scholes


def test_no_jumps_is_black_scholes():
    c = Contract(S=100, K=105, T=0.5, r=0.05, q=0.01, option_type="call")
    assert merton_price(c, 0.2, JumpParams(lam=0.0)) == pytest.approx(
        black_scholes(100, 105, 0.5, 0.05, 0.2, 0.01)["call"], abs=1e-10)


@pytest.mark.parametrize("option_type, K", [("call", 100), ("put", 90), ("call", 120), ("put", 80)])
def test_simulation_matches_closed_form(option_type, K):
    c = Contract(S=100, K=K, T=0.5, r=0.05, option_type=option_type)
    p = JumpParams(lam=2.0, jump_mean=-0.08, jump_vol=0.12)
    mc = price_merton_mc(c, 0.18, p, paths=100_000, seed=3)
    assert abs(mc["price"] - merton_price(c, 0.18, p)) < 4 * mc["stdError"]


def test_put_call_parity():
    p = JumpParams(lam=1.5)
    call = merton_price(Contract(100, 95, 1.0, 0.05, 0.02, "call"), 0.2, p)
    put = merton_price(Contract(100, 95, 1.0, 0.05, 0.02, "put"), 0.2, p)
    assert call - put == pytest.approx(100 * math.exp(-0.02) - 95 * math.exp(-0.05), abs=1e-8)


def test_jumps_make_short_dated_far_otm_options_dearer():
    c = Contract(S=24500, K=22500, T=7 / 365, r=0.065, option_type="put")
    assert merton_price(c, 0.13, JumpParams()) > 3 * black_scholes(24500, 22500, 7 / 365, 0.065, 0.13)["put"]


def test_fan_starts_at_spot_and_is_ordered():
    fan = merton_fan(Contract(100, 100, 0.25, 0.05), 0.2, JumpParams(lam=4), paths=2000, seed=1)
    assert fan["p50"][0] == 100 and fan["p5"][-1] < fan["p50"][-1] < fan["p95"][-1]
