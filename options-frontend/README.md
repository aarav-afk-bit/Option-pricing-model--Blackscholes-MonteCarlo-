# Options Terminal — Frontend

Static dashboard (no build step). Talks to the Flask backend for live NSE
option chain data, computes chart curves client-side.

## Setup

1. Start the backend first (see `backend/README.md`) — it should be running
   on `http://localhost:5000`.
2. Serve this folder with any static server, e.g.:
   ```bash
   cd frontend
   python -m http.server 8080
   ```
3. Open `http://localhost:8080` in your browser.

Opening `index.html` directly via `file://` also mostly works, but a local
server avoids browser fetch/CORS quirks — recommended.

## Pointing at a different backend

If the backend isn't on `localhost:5000` (e.g. deployed elsewhere), set this
before `app.js` loads — add it just above the `<script src="js/app.js">` tag
in `index.html`:

```html
<script>window.OPTIONS_API_BASE = "https://your-backend.example.com";</script>
```

## How it works

1. **Search** — filters `data/nse_companies.json` (a static local reference
   list: sector, lot size) for the autocomplete dropdown.
2. **Select a symbol** — calls `GET /api/option-chain/<symbol>` on the
   backend, which returns the *live* NSE chain: spot price, every expiry, and
   every strike currently trading. The Expiry/Strike dropdowns are populated
   from that response — nothing is hand-typed.
3. **Fetch Live** — calls `GET /api/analyze/<symbol>` for the selected
   strike/expiry/type. The backend pulls the real NSE last-traded-price and
   implied volatility for that exact contract and returns Black-Scholes,
   Greeks, CRR binomial, Monte Carlo, and a buy/sell suggestion — all
   pre-computed server-side.
4. **Recalc Local** — re-runs the same math in `js/pricing.js` against
   whatever is currently in the (editable) parameter strip, without another
   network call. Useful for "what if IV were 30% instead" scenarios.
5. Charts are always drawn client-side from whichever inputs are currently in
   the parameter strip, live or hand-edited.

## Monte Carlo Lab

The section under the pricing cards (`js/mc-lab.js`, `css/mc-lab.css`) prices
the contract in the input strip by simulation next to Black-Scholes:

1. It runs automatically after every **Fetch Live** or **Recalc Local** (or
   press **Run simulation**), showing each model's price with its 95%
   interval, a convergence chart and a fan of simulated price paths.
2. **Calibrate to market** fits the models to today's option chain for the
   selected expiry and plots each model's smile against the market's.
3. **Use calibrated settings** re-prices the contract with the market-fitted
   models, and the scoreboard ranks every model by how close it comes to the
   market price.

The lab is self-contained: it reads the dashboard's inputs and watches the
status line, so `app.js` needs no changes to support it.
