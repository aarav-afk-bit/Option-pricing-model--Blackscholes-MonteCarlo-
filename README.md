# Options Terminal — NSE Black-Scholes Dashboard

Price any NSE stock or index option against its live market premium.

- **[`options-backend/`](options-backend/README.md)** — Flask API. Fetches the
  live option chain from NSE (strikes, expiries, LTP, OI, NSE's implied vol)
  and runs Black-Scholes, Greeks, CRR binomial, Monte Carlo, implied vol,
  liquidity and a fair-value suggestion. Deployed on Render (`render.yaml`).
- **[`options-frontend/`](options-frontend/README.md)** — Static dashboard, no
  build step. Search a symbol, pick an expiry and strike, and it pulls the
  real premium and prices it. Charts and what-if recalculations run in the
  browser (`js/pricing.js` mirrors the backend's `pricing.py`).

## Quick start

```bash
# Terminal 1 — backend
cd options-backend
pip install -r requirements.txt
python app.py                 # http://localhost:5000

# Terminal 2 — frontend
cd options-frontend
python -m http.server 8080    # http://localhost:8080
```

Open `http://localhost:8080`, pick a symbol (e.g. `NIFTY`), an expiry and a
strike, and press **Fetch Live**. To use a deployed backend instead of
localhost, set its URL in `options-frontend/js/config.js`.

## Tests

```bash
cd options-backend && pip install -r requirements-dev.txt && python -m pytest
node --test 'options-frontend/tests/*.test.js'
```

CI runs both on every pull request.

## What "live" means here

The backend calls NSE's public option-chain API (`option-chain-contract-info`
for expiries, `option-chain-v3` for the chain) after the same cookie
handshake a browser does — see `options-backend/nse_client.py`. No prices are
typed in by hand.

Two things worth knowing:
- NSE can rate-limit or block cloud/datacenter IPs. If the deployed backend
  returns persistent 502s, run it from a residential connection or behind a
  proxy.
- It's an unofficial, undocumented endpoint that NSE can change without
  notice. The client is built to be resilient (session refresh, retries,
  short cache) but can't be guaranteed to keep working unmodified.

## Suggestion panel

Compares the live premium to the Black-Scholes fair value and gives a
plain-language read (undervalued / fair / overpriced) with a suggested entry
price, breakeven and theta cost. It's a transparent heuristic on top of the
model — **not investment advice** — and is labelled as such in the UI.
