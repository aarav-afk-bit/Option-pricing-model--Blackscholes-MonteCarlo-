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


def test_convergence_series_narrows_and_reduced_beats_plain():
    from montecarlo.engine import gbm_convergence
    series = gbm_convergence(CASES[0], 0.2, paths=40_000, seed=2)
    paths = [p["paths"] for p in series]
    assert paths == sorted(paths) and paths[-1] == 40_000 and len(series) >= 8
    assert series[-1]["reduced"]["stdError"] < series[0]["reduced"]["stdError"] / 5
    assert all(p["reduced"]["stdError"] < p["plain"]["stdError"] for p in series)
    # The last checkpoint uses all the draws, so it equals the full estimate.
    assert series[-1]["reduced"]["price"] == pytest.approx(price_gbm(CASES[0], 0.2, 40_000, seed=2)["price"])


def test_path_fan_shapes_and_statistics():
    from montecarlo.engine import gbm_fan
    from pricing import black_scholes as bs_
    c = Contract(S=100, K=105, T=0.5, r=0.05, q=0.0, option_type="call")
    fan = gbm_fan(c, 0.25, paths=20_000, steps=40, seed=1)
    assert len(fan["days"]) == 41 and fan["days"][-1] == pytest.approx(182.5)
    assert len(fan["samples"]) == 24 and len(fan["samples"][0]) == 41
    assert fan["p5"][0] == fan["p95"][0] == 100            # every path starts at spot
    bands = zip(fan["p5"], fan["p25"], fan["p50"], fan["p75"], fan["p95"], strict=True)
    assert all(a <= b <= c_ <= d <= e for a, b, c_, d, e in bands)
    # Share finishing ITM matches the risk-neutral N(d2).
    from scipy.stats import norm
    d2 = bs_(100, 105, 0.5, 0.05, 0.25)["d2"]
    assert fan["finalItmShare"] == pytest.approx(norm.cdf(d2), abs=0.01)
