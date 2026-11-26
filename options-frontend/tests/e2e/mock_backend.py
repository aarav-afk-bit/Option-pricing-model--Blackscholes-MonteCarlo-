"""
Run the real Flask backend with NSE replaced by a deterministic fake option
chain, for the browser tests. Expiries are relative to today, so the tests
never go stale.

    python options-frontend/tests/e2e/mock_backend.py   # serves http://localhost:5000
"""

import math
import os
import sys
from datetime import date, timedelta

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "options-backend"))
sys.path.insert(0, BACKEND)

import nse_client  # noqa: E402
from app import app  # noqa: E402
from pricing import black_scholes  # noqa: E402

SPOT = 24512.35
EXPIRY_DATES = [date.today() + timedelta(days=d) for d in (35, 63)]
EXPIRIES = [d.strftime("%d-%b-%Y") for d in EXPIRY_DATES]


def leg(strike, expiry_date, side):
    T = max((expiry_date - date.today()).days, 1) / 365
    iv = 0.13 + 10 * ((strike - SPOT) / SPOT) ** 2 + (0.01 if side == "PE" else 0)   # a smile
    price = black_scholes(SPOT, strike, T, 0.065, iv)["call" if side == "CE" else "put"]
    oi = int(50000 * math.exp(-abs(strike - (24800 if side == "CE" else 24200)) / 400))
    return {"strikePrice": strike, "lastPrice": round(price, 2), "impliedVolatility": round(iv * 100, 2),
            "openInterest": oi, "changeinOpenInterest": oi // 10, "totalTradedVolume": oi // 3,
            "bidprice": round(price * 0.99, 2), "bidQty": 75, "askPrice": round(price * 1.01, 2), "askQty": 150,
            "underlyingValue": SPOT}


def fake_get_json(self, url, params=None, retries=2):
    if url.endswith("option-chain-contract-info"):
        return {"expiryDates": EXPIRIES}
    if url.endswith("option-chain-v3"):
        expiry = params["expiry"]
        when = EXPIRY_DATES[EXPIRIES.index(expiry)]
        return {"records": {"underlyingValue": SPOT, "data": [
            {"expiryDates": expiry, "strikePrice": k, "CE": leg(k, when, "CE"), "PE": leg(k, when, "PE")}
            for k in range(23500, 25550, 100)]}}
    return {}


nse_client.NSEClient._get_json = fake_get_json
nse_client.NSEClient._refresh_session = lambda self: None

if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)))
