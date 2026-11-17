"""
Monte Carlo Lab API.

  GET /api/montecarlo?spot=&strike=&days=&rate=&div=&vol=&type=call|put&paths=&seed=

Prices one contract with Black-Scholes and every Monte Carlo model side by
side. Inputs are passed explicitly (not fetched from NSE) so the lab works
on live values and on what-if edits alike. Units match the dashboard's
input strip: rate, div and vol are percentages; days are calendar days.
"""

import math
import time

from flask import Blueprint, jsonify, request

from montecarlo.engine import Contract, gbm_convergence, gbm_fan, price_gbm
from pricing import black_scholes

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


def run_models(contract, sigma, paths, seed):
    """Every Monte Carlo model in the lab, keyed by id. Later models plug in here."""
    return {
        "gbm": {
            "label": "Monte Carlo (constant vol)",
            "description": "Same assumptions as Black-Scholes, priced by simulation. Should agree with it.",
            **price_gbm(contract, sigma, paths, seed),
        },
    }


@mc_api.get("/api/montecarlo")
def montecarlo():
    try:
        contract, sigma, paths, seed = parse_request()
    except BadInput as exc:
        return jsonify({"error": str(exc)}), 400

    started = time.perf_counter()
    bs = black_scholes(contract.S, contract.K, contract.T, contract.r, sigma, contract.q)
    models = run_models(contract, sigma, paths, seed)
    return jsonify({
        "inputs": {"spot": contract.S, "strike": contract.K, "days": round(contract.T * 365, 4),
                   "rate": contract.r, "div": contract.q, "vol": sigma,
                   "type": contract.option_type, "paths": paths, "seed": seed},
        "blackScholes": {"price": bs["call"] if contract.is_call else bs["put"]},
        "models": models,
        "convergence": gbm_convergence(contract, sigma, paths, seed),
        "fan": gbm_fan(contract, sigma, seed=seed),
        "elapsedMs": round((time.perf_counter() - started) * 1000, 1),
    })
