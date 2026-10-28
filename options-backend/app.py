"""
Options Terminal — Backend API

Endpoints:
  GET /api/health
  GET /api/symbols
  GET /api/option-chain/<symbol>?expiry=..
  GET /api/analyze/<symbol>?strike=..&expiry=..&type=call|put&r=..&q=..&sigma=..

  Units for /api/analyze: r is a decimal (0.065 = 6.5%), q and sigma are
  percentages (1.2 = 1.2%).

Run:
  pip install -r requirements.txt
  python app.py
  (serves on http://localhost:5000)
"""

import json
import logging
import math
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

import config
from liquidity import liquidity_summary
from nse_client import nse_client, INDEX_SYMBOLS
from pricing import (
    black_scholes,
    greeks,
    crr_price,
    monte_carlo,
    implied_volatility,
    build_suggestion,
)

app = Flask(__name__)

# In production, lock this down to your actual Vercel domain via the
# FRONTEND_ORIGIN env var (comma-separated if you have more than one, e.g.
# a preview + production URL). Defaults to "*" for local development.
_allowed_origins = os.environ.get("FRONTEND_ORIGIN", "*")
CORS(app, origins=_allowed_origins.split(",") if _allowed_origins != "*" else "*")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("options_terminal")


# The frontend always reads `error` from a JSON body, so errors must never
# come back as Flask's default HTML pages.
@app.errorhandler(HTTPException)
def http_error(exc):
    return jsonify({"error": exc.description, "status": exc.code}), exc.code


@app.errorhandler(Exception)
def unexpected_error(exc):
    log.exception("Unhandled error on %s %s", request.method, request.path)
    return jsonify({"error": "internal server error", "status": 500}), 500

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
IST = ZoneInfo("Asia/Kolkata")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _leg_summary(leg):
    if not leg:
        return None
    return {
        "lastPrice": leg.get("lastPrice"),
        "impliedVolatility": leg.get("impliedVolatility"),
        "openInterest": leg.get("openInterest"),
        "changeInOpenInterest": leg.get("changeinOpenInterest"),
        "volume": leg.get("totalTradedVolume"),
        "bid": leg.get("bidprice"),
        "bidQty": leg.get("bidQty"),
        "ask": leg.get("askPrice"),
        "askQty": leg.get("askQty"),
        "change": leg.get("change"),
    }


def _days_to_expiry(expiry_str):
    expiry_dt = datetime.strptime(expiry_str, "%d-%b-%Y")
    # NSE expiries are Indian dates; the server (e.g. Render) runs in UTC.
    delta_days = (expiry_dt.date() - datetime.now(IST).date()).days
    return max(delta_days, 0) + 1  # settlement-day inclusive, floor at 1 day


def _float_arg(name, default=None):
    """Parse an optional numeric query param; raises ValueError on junk/NaN."""
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(name)
    return value


def _by_side(values, option_type):
    """Pick the call or put entry from a {"call": ..., "put": ...} dict."""
    return values["call"] if option_type == "call" else values["put"]


def _find_leg(records, expiry, strike, option_type):
    """
    Locate one contract in a normalised NSE chain.

    Returns (row, leg): row is None if the strike/expiry isn't listed, and leg
    is None if the row has no CE/PE side for `option_type`. Strikes are
    compared as floats because NSE may send 24500 or 24500.0.
    """
    for row in records.get("data", []):
        if row.get("expiryDate") == expiry and abs(float(row.get("strikePrice")) - strike) < 1e-6:
            return row, row.get("CE" if option_type == "call" else "PE")
    return None, None


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


@app.route("/api/symbols")
def symbols():
    """Static reference list used for the search box (sector, lot size, etc)."""
    path = os.path.join(DATA_DIR, "nse_symbols.json")
    with open(path) as f:
        return jsonify(json.load(f))


@app.route("/api/option-chain/<symbol>")
def option_chain(symbol):
    """
    Live option chain for a symbol: every strike x expiry currently trading on
    NSE, pulled directly from NSE's option-chain API — no manual data entry.
    """
    symbol = symbol.upper()
    expiry = request.args.get("expiry") or None
    try:
        raw = nse_client.get_option_chain(symbol, expiry=expiry)
    except RuntimeError as exc:
        return jsonify({"error": f"could not fetch live NSE data: {exc}"}), 502

    records = raw.get("records", {})
    spot = records.get("underlyingValue")
    expiries = records.get("expiryDates", [])

    strikes_set = set()
    chain = {}
    for row in records.get("data", []):
        expiry = row.get("expiryDate")
        strike = row.get("strikePrice")
        if expiry is None or strike is None:
            continue
        strikes_set.add(strike)
        chain.setdefault(expiry, {})[str(strike)] = {
            "CE": _leg_summary(row.get("CE")),
            "PE": _leg_summary(row.get("PE")),
        }

    return jsonify({
        "symbol": symbol,
        "isIndex": symbol in INDEX_SYMBOLS,
        "spot": spot,
        "expiries": expiries,
        "strikes": sorted(strikes_set),
        "chain": chain,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/analyze/<symbol>")
def analyze(symbol):
    """
    Full pricing workup for one specific contract (symbol + strike + expiry +
    type), auto-pulling the live NSE premium as the market price and running
    Black-Scholes, Greeks, CRR, Monte Carlo, implied vol and the suggestion
    heuristic against it.
    """
    symbol = symbol.upper()
    try:
        strike = float(request.args["strike"])
        expiry = request.args["expiry"]
        datetime.strptime(expiry, "%d-%b-%Y")
    except (KeyError, ValueError):
        return jsonify({"error": "strike and expiry (DD-Mon-YYYY) query params are required"}), 400

    option_type = request.args.get("type", "call").lower()
    if option_type not in ("call", "put"):
        return jsonify({"error": "type must be 'call' or 'put'"}), 400

    try:
        r = _float_arg("r", config.RISK_FREE_RATE)
        q_override = _float_arg("q")
        sigma_override = _float_arg("sigma")
    except ValueError:
        return jsonify({"error": "r, q and sigma must be numbers"}), 400
    if sigma_override is not None and sigma_override <= 0:
        return jsonify({"error": "sigma must be a positive percentage"}), 400

    try:
        raw = nse_client.get_option_chain(symbol, expiry=expiry)
    except RuntimeError as exc:
        return jsonify({"error": f"could not fetch live NSE data: {exc}"}), 502

    records = raw.get("records", {})
    spot = records.get("underlyingValue")
    if spot is None:
        return jsonify({"error": "NSE did not return an underlying price for this symbol"}), 502

    row, leg = _find_leg(records, expiry, strike, option_type)
    if row is None:
        return jsonify({"error": "that strike/expiry is not in the live NSE chain"}), 404
    if leg is None:
        return jsonify({"error": f"no live {option_type} data for this strike/expiry"}), 404

    market_price = leg.get("lastPrice") or None
    nse_iv = leg.get("impliedVolatility") or None  # already a percentage, e.g. 24.5

    days = _days_to_expiry(expiry)
    T = days / 365

    if sigma_override is not None:
        sigma = sigma_override / 100
    elif nse_iv:
        sigma = nse_iv / 100
    else:
        sigma = config.FALLBACK_SIGMA  # NSE hasn't computed an IV yet (e.g. illiquid strike)

    q = q_override / 100 if q_override is not None else 0.0

    bs = black_scholes(spot, strike, T, r, sigma, q)
    gk = greeks(spot, strike, T, r, sigma, q)
    crr_euro = crr_price(spot, strike, T, r, sigma, q, config.CRR_STEPS, option_type, american=False)
    crr_amer = crr_price(spot, strike, T, r, sigma, q, config.CRR_STEPS, option_type, american=True)
    mc_price, mc_se = monte_carlo(spot, strike, T, r, sigma, q, config.MC_SIMULATIONS, option_type)
    solved_iv = implied_volatility(market_price, spot, strike, T, r, q, option_type)
    fair_value = _by_side(bs, option_type)
    liquidity = liquidity_summary(leg, fair_value)
    # IV from the bid/ask mid is often more trustworthy than from a stale LTP.
    mid_iv = implied_volatility(liquidity["mid"], spot, strike, T, r, q, option_type)

    suggestion = build_suggestion(strike, option_type, fair_value, market_price, gk)

    return jsonify({
        "symbol": symbol,
        "spot": spot,
        "strike": strike,
        "expiry": expiry,
        "daysToExpiry": days,
        "optionType": option_type,
        "inputs": {"r": r, "sigma": sigma, "q": q},
        "market": {
            "lastPrice": market_price,
            "nseImpliedVolatility": nse_iv,
            "openInterest": leg.get("openInterest"),
            "volume": leg.get("totalTradedVolume"),
            "bid": leg.get("bidprice"),
            "ask": leg.get("askPrice"),
        },
        "liquidity": liquidity,
        "blackScholes": bs,
        "greeks": gk,
        "crr": {
            "european": crr_euro,
            "american": crr_amer,
            "earlyExercisePremium": crr_amer - crr_euro,
        },
        "monteCarlo": {"price": mc_price, "stdError": mc_se},
        "impliedVolatility": {
            "solved": solved_iv,
            "solvedFromMid": mid_iv,
            "nseReported": (nse_iv / 100) if nse_iv else None,
        },
        "suggestion": suggestion,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    })


if __name__ == "__main__":
    # Local dev only. In production (Render) gunicorn imports `app` directly
    # and this block never runs — see Procfile / render.yaml.
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
