"""
Monte Carlo Lab API.

  GET /api/montecarlo?spot=&strike=&days=&rate=&div=&vol=&type=call|put&paths=&seed=
      optional Heston settings: hVol0=&hVolLong=&hKappa=&hXi=&hRho=  (vols in %)
      optional jump settings:   jLambda=&jMean=&jVol=                (jumps/year, sizes in %)

Prices one contract with Black-Scholes and every Monte Carlo model side by
side. Inputs are passed explicitly (not fetched from NSE) so the lab works
on live values and on what-if edits alike. Units match the dashboard's
input strip: rate, div and vol are percentages; days are calendar days.
"""

import math
import time

from flask import Blueprint, jsonify, request

from montecarlo.american import price_american_lsm
from montecarlo.engine import Contract, gbm_convergence, gbm_fan, price_gbm
from montecarlo.heston import HestonParams, heston_fan, heston_price_cf, price_heston_mc
from montecarlo.jumps import JumpParams, merton_fan, merton_price, price_merton_mc
from pricing import black_scholes, crr_price

mc_api = Blueprint("montecarlo", __name__)

MIN_PATHS, MAX_PATHS, DEFAULT_PATHS = 1_000, 200_000, 50_000


class BadInput(ValueError):
    pass


def _num(name, default=None, low=None, high=None):
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        if default is None:
            raise BadInput(f"{name} is required")
        return default
    try:
        value = float(raw)
    except ValueError:
        raise BadInput(f"{name} must be a number") from None
    if not math.isfinite(value) or (low is not None and value < low) or (high is not None and value > high):
        raise BadInput(f"{name} must be between {low} and {high}")
    return value


def parse_request():
    """Validated contract, volatility (decimal) and simulation settings from the query string."""
    option_type = request.args.get("type", "call").lower()
    if option_type not in ("call", "put"):
        raise BadInput("type must be 'call' or 'put'")
    contract = Contract(
        S=_num("spot", low=0.01, high=1e7),
        K=_num("strike", low=0.01, high=1e7),
        T=_num("days", low=0.5, high=3650) / 365,
        r=_num("rate", 6.5, low=-5, high=50) / 100,
        q=_num("div", 0.0, low=0, high=50) / 100,
        option_type=option_type,
    )
    sigma = _num("vol", low=0.5, high=500) / 100
    paths = int(_num("paths", DEFAULT_PATHS, low=MIN_PATHS, high=MAX_PATHS))
    seed = request.args.get("seed")
    seed = int(seed) if seed and seed.isdigit() else None
    return contract, sigma, paths, seed


def _variance(name, default):
    """Variance from a volatility given in %, or `default` when the parameter is absent."""
    if not (request.args.get(name) or "").strip():
        return default
    return (_num(name, low=0.5, high=500) / 100) ** 2


def parse_heston(sigma):
    """Heston settings from the query string; defaults are centred on today's vol."""
    base = HestonParams.from_vol(sigma)
    return HestonParams(
        v0=_variance("hVol0", base.v0),
        theta=_variance("hVolLong", base.theta),
        kappa=_num("hKappa", base.kappa, low=0.01, high=50),
        xi=_num("hXi", base.xi, low=0.01, high=5),
        rho=_num("hRho", base.rho, low=-0.99, high=0.99),
    )


def parse_jumps():
    base = JumpParams()
    return JumpParams(
        lam=_num("jLambda", base.lam, low=0, high=50),
        jump_mean=_num("jMean", base.jump_mean * 100, low=-50, high=50) / 100,
        jump_vol=_num("jVol", base.jump_vol * 100, low=0.1, high=100) / 100,
    )


def run_models(contract, sigma, paths, seed, heston, jumps):
    """Every Monte Carlo model in the lab, keyed by id. Later models plug in here."""
    return {
        "gbm": {
            "label": "Monte Carlo (constant vol)",
            "description": "Same assumptions as Black-Scholes, priced by simulation. Should agree with it.",
            **price_gbm(contract, sigma, paths, seed),
        },
        "heston": {
            "label": "Heston (stochastic vol)",
            "description": "Volatility moves randomly and rises when prices fall, so big downside moves are "
                           "likelier than Black-Scholes assumes.",
            "params": heston.as_dict(),
            "formulaPrice": heston_price_cf(contract, heston),
            **price_heston_mc(contract, heston, paths, seed),
        },
        "jumps": {
            "label": "Merton (jumps)",
            "description": "Adds sudden gaps (results, budget day, global shocks) on top of normal moves, "
                           "so far-from-the-money options are worth more.",
            "params": jumps.as_dict(),
            "formulaPrice": merton_price(contract, sigma, jumps),
            **price_merton_mc(contract, sigma, jumps, paths, seed),
        },
        "american": {
            "label": "American (early exercise)",
            "description": "Longstaff-Schwartz: decides on every simulated day whether exercising beats holding. "
                           "NSE options are European; this shows what early exercise would be worth.",
            # Regression at every step is the costliest model, so it gets at most 40,000 paths.
            **price_american_lsm(contract, sigma, min(paths, 40_000), seed=seed),
            "formulaPrice": crr_price(contract.S, contract.K, contract.T, contract.r, sigma, contract.q,
                                      500, contract.option_type, american=True),
            "checkLabel": "Binomial tree check",
        },
    }


def fans(contract, sigma, seed, heston, jumps):
    if contract.T <= 0:
        return {}
    return {
        "gbm": gbm_fan(contract, sigma, seed=seed),
        "heston": heston_fan(contract, heston, seed=seed),
        "jumps": merton_fan(contract, sigma, jumps, seed=seed),
    }


@mc_api.get("/api/montecarlo")
def montecarlo():
    try:
        contract, sigma, paths, seed = parse_request()
        heston = parse_heston(sigma)
        jumps = parse_jumps()
    except BadInput as exc:
        return jsonify({"error": str(exc)}), 400

    started = time.perf_counter()
    bs = black_scholes(contract.S, contract.K, contract.T, contract.r, sigma, contract.q)
    models = run_models(contract, sigma, paths, seed, heston, jumps)
    return jsonify({
        "inputs": {"spot": contract.S, "strike": contract.K, "days": round(contract.T * 365, 4),
                   "rate": contract.r, "div": contract.q, "vol": sigma,
                   "type": contract.option_type, "paths": paths, "seed": seed},
        "blackScholes": {"price": bs["call"] if contract.is_call else bs["put"]},
        "models": models,
        "convergence": gbm_convergence(contract, sigma, paths, seed),
        "fans": fans(contract, sigma, seed, heston, jumps),
        "elapsedMs": round((time.perf_counter() - started) * 1000, 1),
    })
