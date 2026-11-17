"""Longstaff-Schwartz American pricing agrees with the CRR binomial tree."""

import pytest

from montecarlo.american import price_american_lsm
from montecarlo.engine import Contract
from pricing import crr_price


@pytest.mark.parametrize("S, K", [(100, 110), (100, 100), (100, 90)])
def test_american_put_matches_binomial_tree(S, K):
    c = Contract(S=S, K=K, T=1.0, r=0.08, option_type="put")
    lsm = price_american_lsm(c, 0.25, paths=60_000, steps=50, seed=2)
    tree = crr_price(S, K, 1.0, 0.08, 0.25, 0.0, 500, "put", american=True)
    # LSM is slightly low-biased (its exercise rule is estimated); allow ~1% plus noise.
    assert abs(lsm["price"] - tree) < 4 * lsm["stdError"] + 0.01 * tree


def test_deep_itm_put_has_a_real_early_exercise_premium():
    c = Contract(S=80, K=100, T=1.0, r=0.08, option_type="put")
    lsm = price_american_lsm(c, 0.2, paths=40_000, seed=1)
    assert lsm["earlyExercisePremium"] > 0.5
    assert lsm["exerciseShare"] > 0.5


def test_call_without_dividends_is_never_worth_exercising_early():
    c = Contract(S=100, K=95, T=0.5, r=0.06, option_type="call")
    lsm = price_american_lsm(c, 0.2, paths=40_000, seed=1)
    assert lsm["earlyExercisePremium"] < 0.02 * lsm["price"]


def test_expired_option_is_intrinsic():
    assert price_american_lsm(Contract(90, 100, 0, 0.05, option_type="put"), 0.2)["price"] == 10
