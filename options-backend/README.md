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

## Monte Carlo Lab

Simulation-based pricing that runs side by side with Black-Scholes
(`montecarlo/` package, routes in `mc_routes.py`).

| Model | File | What it adds over Black-Scholes | Checked against |
|---|---|---|---|
| Constant vol | `engine.py` | Nothing — the sanity check. Antithetic variates + a control variate make it ~25× more efficient than plain MC | Black-Scholes |
| Heston | `heston.py` | Volatility moves randomly and rises when prices fall (skew). Simulated with Andersen's QE scheme | Heston's Fourier formula |
| Merton jumps | `jumps.py` | Sudden gaps on top of normal moves (fat tails), simulated exactly | Merton's series formula |
| American | `american.py` | Early exercise, by Longstaff-Schwartz regression | CRR binomial tree |

`calibrate.py` fits Black-Scholes (one vol), Heston and Merton to the live
option chain for one expiry and reports each fit's error in implied-vol
points — this is where the richer models beat Black-Scholes, which cannot
reproduce the volatility smile.

```bash
# Price one contract with every model (rate/div/vol in %, days = calendar days)
curl "http://localhost:5000/api/montecarlo?spot=24512&strike=24500&days=30&vol=13&type=call&paths=50000"

# Optional model settings: hVol0, hVolLong, hKappa, hXi, hRho (Heston),
#                          jDiffVol, jLambda, jMean, jVol (Merton); seed for repeatable runs

# Fit the models to today's chain; `labSettings` plugs back into the call above
curl "http://localhost:5000/api/montecarlo/calibrate/NIFTY?expiry=30-Dec-2026&rate=6.5"
```

`paths` is limited to 1,000–200,000; American pricing uses at most 40,000.
A 50,000-path request with every model takes about a second.

Both endpoints are rate-limited per visitor (`ratelimit.py`) so one person
or script can't monopolise the server: a 50,000-path run costs 1 unit, a
calibration 2, and each visitor can spend up to 12 at once, regaining 20 a
minute. Over the limit the API returns HTTP 429 with a `Retry-After` header.
Tune with `RATE_LIMIT_PER_MINUTE` (0 turns it off), `RATE_LIMIT_BURST` and
`TRUSTED_PROXY_HOPS` (how many proxies append to `X-Forwarded-For`; 1 on Render).
