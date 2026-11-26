"""
Market-wide analytics that look across several expiries.

  GET /api/term-structure/<symbol>?max=6

At-the-money implied volatility for each of the next `max` expiries (the
"term structure"). An upward slope means the market expects calmer
conditions now than later; an inverted one usually means it is pricing an
event soon (results, policy, an election).
"""

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request

from nse_client import nse_client

analytics_api = Blueprint("analytics", __name__)
IST = ZoneInfo("Asia/Kolkata")
MAX_EXPIRIES = 8


def _leg_iv(row, side):
    leg = row.get(side) or {}
    iv = leg.get("impliedVolatility") or 0
    return float(iv) if iv > 0 else None


def atm_iv(rows, spot):
    """
    At-the-money implied volatility (in %): the call/put average at each strike
    (whichever exists), linearly interpolated between the two strikes around spot.
    Returns (iv, nearest_strike) or (None, None) if no strike has an IV.
    """
    points = []
    for row in rows:
        ivs = [v for v in (_leg_iv(row, "CE"), _leg_iv(row, "PE")) if v is not None]
        if ivs:
            points.append((float(row["strikePrice"]), sum(ivs) / len(ivs)))
    if not points:
        return None, None
    points.sort()
    nearest = min(points, key=lambda p: abs(p[0] - spot))[0]
    below = [p for p in points if p[0] <= spot]
    above = [p for p in points if p[0] >= spot]
    if below and above:
        (k1, v1), (k2, v2) = below[-1], above[0]
        iv = v1 if k2 == k1 else v1 + (v2 - v1) * (spot - k1) / (k2 - k1)
    else:  # spot is outside the listed strikes: use the closest one
        iv = below[-1][1] if below else above[0][1]
    return iv, nearest


def _days_to(expiry):
    expiry_date = datetime.strptime(expiry, "%d-%b-%Y").date()
    return max((expiry_date - datetime.now(IST).date()).days, 0) + 1   # same convention as /api/analyze


@analytics_api.get("/api/term-structure/<symbol>")
def term_structure(symbol):
    symbol = symbol.upper()
    try:
        limit = int(request.args.get("max", 6))
    except ValueError:
        return jsonify({"error": "max must be a whole number"}), 400
    limit = min(max(limit, 1), MAX_EXPIRIES)

    try:
        expiries = nse_client.get_expiries(symbol)[:limit]
    except RuntimeError as exc:
        return jsonify({"error": f"could not fetch live NSE data: {exc}"}), 502
    if not expiries:
        return jsonify({"error": f"NSE lists no option expiries for {symbol}"}), 404

    points, spot, skipped = [], None, []
    for expiry in expiries:
        try:
            raw = nse_client.get_option_chain(symbol, expiry=expiry)
        except RuntimeError:
            skipped.append(expiry)
            continue
        records = raw.get("records", {})
        spot = records.get("underlyingValue") or spot
        rows = [r for r in records.get("data", []) if r.get("expiryDate") == expiry]
        iv, strike = atm_iv(rows, spot) if spot else (None, None)
        if iv is None:
            skipped.append(expiry)
            continue
        days = _days_to(expiry)
        move_pct = iv / 100 * math.sqrt(days / 365)   # one standard deviation by expiry
        points.append({
            "expiry": expiry, "days": days, "atmIv": round(iv, 3), "atmStrike": strike,
            "expectedMovePct": round(move_pct * 100, 3),
            "expectedMove": round(spot * move_pct, 2),
        })

    if len(points) >= 2:
        slope = points[-1]["atmIv"] - points[0]["atmIv"]
        shape = "upward" if slope > 0.5 else "inverted" if slope < -0.5 else "flat"
    else:
        shape = "flat"
    return jsonify({"symbol": symbol, "spot": spot, "points": points, "shape": shape, "skipped": skipped})
