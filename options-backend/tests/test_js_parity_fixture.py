"""
Shared reference values for the JavaScript pricing mirror (js/pricing.js).

The fixture options-frontend/tests/fixtures/pricing_cases.json holds inputs and
the outputs pricing.py gives for them; options-frontend/tests/pricing.test.js
checks pricing.js against the same file. This test fails if pricing.py and the
fixture drift apart, so the two languages are always compared on current values.

After an intentional change to pricing.py, regenerate it from options-backend/:
    python tests/test_js_parity_fixture.py --write
"""

import itertools
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pricing import black_scholes, crr_price, greeks  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "..", "options-frontend", "tests", "fixtures",
                       "pricing_cases.json")
CRR_STEPS = 100


def build_cases():
    cases = []
    grid = itertools.product(
        [100.0, 1342.5, 24512.35],   # spot
        [0.9, 1.0, 1.1],             # strike / spot
        [7 / 365, 0.25, 1.0],        # years to expiry
        [0.12, 0.35],                # volatility
        [0.0, 0.015],                # dividend yield
    )
    for S, moneyness, T, sigma, q in grid:
        K, r = round(S * moneyness, 2), 0.065
        bs = black_scholes(S, K, T, r, sigma, q)
        cases.append({
            "inputs": {"S": S, "K": K, "T": T, "r": r, "sigma": sigma, "q": q},
            "blackScholes": {"call": bs["call"], "put": bs["put"], "d1": bs["d1"], "d2": bs["d2"]},
            "greeks": greeks(S, K, T, r, sigma, q),
            "crr": {
                f"{side}_{style}": crr_price(S, K, T, r, sigma, q, CRR_STEPS, side, american=(style == "american"))
                for side in ("call", "put") for style in ("european", "american")
            },
        })
    return {"crrSteps": CRR_STEPS, "cases": cases}


def test_fixture_matches_pricing_py():
    with open(FIXTURE) as f:
        stored = json.load(f)
    fresh = build_cases()
    assert stored["crrSteps"] == fresh["crrSteps"]
    assert len(stored["cases"]) == len(fresh["cases"])
    for old, new in zip(stored["cases"], fresh["cases"], strict=True):
        assert old["inputs"] == new["inputs"]
        for group in ("blackScholes", "greeks", "crr"):
            for key, value in new[group].items():
                assert old[group][key] == pytest.approx(value, rel=1e-12, abs=1e-12), (old["inputs"], group, key)


if __name__ == "__main__":
    if "--write" not in sys.argv:
        sys.exit("usage: python tests/test_js_parity_fixture.py --write")
    with open(FIXTURE, "w") as f:
        json.dump(build_cases(), f, indent=1)
        f.write("\n")
    print(f"wrote {os.path.normpath(FIXTURE)}")
