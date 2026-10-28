# Options Terminal — Backend

Flask API that pulls **live option chain data directly from NSE** (strikes,
expiries, last traded price, open interest, NSE's own implied volatility) and
runs it through a Black-Scholes / CRR binomial / Monte Carlo pricing engine.

No manual data entry is required for the market side — point it at a symbol
and a strike/expiry, and it fetches the real thing.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Runs on `http://localhost:5000`.

## Deploying on Render

**New service (Blueprint):** Render dashboard → **New → Blueprint** → pick this
repo. Render reads `render.yaml` from the repo root and creates the web
service with everything below already filled in.

**Existing service (set up by hand):** open it → **Settings** and set:

| Setting | Value |
|---|---|
| Root Directory | `options-backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --timeout 120 --workers 1 --threads 4` |
| Health Check Path | `/api/health` |
| Env var `PYTHON_VERSION` | `3.11.9` |
| Env var `FRONTEND_ORIGIN` | your Vercel URL (or `*`) |

Optional tuning variables (see `config.py`; invalid values fall back to the default):

| Env var | Default | Meaning |
|---|---|---|
| `RISK_FREE_RATE` | `0.065` | r used when a request doesn't pass one (decimal) |
| `FALLBACK_SIGMA` | `0.25` | volatility when NSE reports no IV for a strike (decimal) |
| `CRR_STEPS` | `150` | binomial tree steps |
| `MC_SIMULATIONS` | `30000` | Monte Carlo paths |

Then **Manual Deploy → Deploy latest commit**. Check
`https://<your-service>.onrender.com/api/health` returns `{"status": "ok"}`,
and put that base URL in `options-frontend/js/config.js`.

The free plan sleeps after ~15 minutes idle; the first request afterwards
takes ~30–60s (the frontend retries while it wakes up).

## Tests and lint

```bash
pip install -r requirements-dev.txt
python -m pytest     # unit + API tests, no network needed
ruff check .         # lint (settings in ruff.toml)
```

Both run in CI on every pull request.

## How the NSE fetch works

`nse_client.py` opens a `requests.Session()`, first loads `nseindia.com` and
`nseindia.com/option-chain` (this is what hands you the cookies NSE's API
checks for), then calls NSE's current (v3) endpoints:

- `https://www.nseindia.com/api/option-chain-contract-info?symbol=NIFTY` (expiry list)
- `https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry=30-Sep-2025`
- `https://www.nseindia.com/api/option-chain-v3?type=Equity&symbol=RELIANCE&expiry=30-Sep-2025`

The v3 API returns one expiry per request. The old `option-chain-indices` /
`option-chain-equities` endpoints were retired by NSE in 2025 (they now return
`{}`) and are only used as a fallback.

Responses are cached in-memory for 5 seconds (configurable) so rapid UI
interaction doesn't hammer NSE, and the session auto-refreshes if a request
fails or every 4 minutes.

**Things to know:**
- NSE rate-limits and sometimes blocks datacenter/cloud IPs. If you deploy
  this on AWS/GCP/a VPS and get persistent `502`s, try running it from a
  residential connection, or put it behind a proxy with a residential exit IP.
- This is NSE's public but *unofficial* endpoint — it can change shape or
  block scripted access without notice. Treat it as best-effort, not a
  guaranteed feed, and don't hit it faster than a real user would.
- Index option chains (`NIFTY`, `BANKNIFTY`, `FINNIFTY`, `MIDCPNIFTY`) use
  `type=Indices`, single-stock options use `type=Equity` — the client picks
  the right one automatically.
- On Render, Python is pinned to 3.11 via `.python-version` / `PYTHON_VERSION`
  (Render ignores `runtime.txt`, and the pinned numpy/scipy have no wheels
  for Render's default Python 3.13).

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness check |
| GET | `/api/symbols` | Static reference list (sector, lot size) for the search box |
| GET | `/api/option-chain/<symbol>?expiry=` | Live chain: spot, all expiries, and CE/PE LTP/IV/OI for one expiry (nearest if omitted) |
| GET | `/api/analyze/<symbol>?strike=&expiry=&type=call\|put&r=&q=&sigma=` | Black-Scholes, Greeks, CRR, Monte Carlo, implied vol and the buy/sell suggestion for one live contract. `r` is a decimal (`0.065`); `q` and `sigma` are percentages (`1.5`, `18`) |

`expiry` must be passed exactly as returned by `/api/option-chain` (NSE's own
`DD-Mon-YYYY` format, e.g. `28-Aug-2025`).

### Example

```bash
curl "http://localhost:5000/api/option-chain/RELIANCE"
curl "http://localhost:5000/api/analyze/RELIANCE?strike=1340&expiry=28-Aug-2025&type=call"
```
