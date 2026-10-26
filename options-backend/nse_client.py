"""
Lightweight client for NSE India's public (unofficial) option-chain API.

NSE serves option chain data as JSON from (current "v3" API):
  https://www.nseindia.com/api/option-chain-contract-info?symbol=NIFTY
      -> list of live expiry dates (and strikes) for the symbol
  https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry=30-Sep-2025
  https://www.nseindia.com/api/option-chain-v3?type=Equity&symbol=RELIANCE&expiry=30-Sep-2025
      -> the chain for ONE expiry

The older endpoints (api/option-chain-indices / api/option-chain-equities)
were retired by NSE in 2025 and now return an empty `{}`; they are only kept
here as a fallback.

These endpoints are only reachable with a browser-like session: you must first
load nseindia.com in the same requests.Session() so it hands you the cookies
(nsit / nseappid / etc.) that the API checks for on every subsequent call.
This client handles that handshake, retries, and a short-lived cache so the
dashboard doesn't hammer NSE on every UI interaction.

Notes / known limitations:
- NSE aggressively rate-limits and sometimes blocks datacenter / cloud IPs.
  If you're deploying this on a cloud VM and getting persistent 403s, run it
  from a residential connection or add your own proxy.
- Cookies expire; this client refreshes the session automatically on failure
  and periodically in the background.
- This talks to a public, undocumented endpoint that NSE can change without
  notice. Treat it as best-effort market data, not a guaranteed feed.
"""

import logging
import threading
import time

import requests

NSE_BASE = "https://www.nseindia.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    # No "br": requests can't decode Brotli unless the optional `brotli`
    # package is installed, and NSE happily answers in Brotli when offered —
    # which made every response look like "invalid JSON".
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Referer": "https://www.nseindia.com/option-chain",
}

INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}

log = logging.getLogger(__name__)


class NSEClient:
    def __init__(self, cache_ttl_seconds=5, session_ttl_seconds=240, max_cache_entries=256):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._lock = threading.Lock()
        self._last_refresh = 0.0
        self._cache = {}  # key -> (stored_at, data); insertion order = least recently used first
        self.max_cache_entries = max_cache_entries
        self.cache_ttl = cache_ttl_seconds
        self.session_ttl = session_ttl_seconds
        # No network here: the cookie handshake happens lazily on the first
        # data request (_last_refresh=0 marks the session as stale), so
        # importing the app — gunicorn boot, tests — never waits on NSE.

    def _refresh_session(self):
        try:
            self.session.get(NSE_BASE, timeout=6)
            self.session.get(f"{NSE_BASE}/option-chain", timeout=6)
            self._last_refresh = time.time()
        except requests.RequestException:
            # Will retry on the next actual data call.
            pass

    def _get_json(self, url, params=None, retries=2):
        last_status = None
        for attempt in range(retries + 1):
            if time.time() - self._last_refresh > self.session_ttl:
                self._refresh_session()
            try:
                resp = self.session.get(url, params=params, timeout=8)
            except requests.RequestException as exc:
                last_status = str(exc)
                self._refresh_session()
                time.sleep(0.5)
                continue

            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    last_status = "invalid JSON in response"
            else:
                last_status = resp.status_code

            # 401/403/429 usually mean the session cookie is stale or NSE is
            # rate-limiting us — refresh and back off before retrying.
            self._refresh_session()
            time.sleep(0.6 * (attempt + 1))

        log.warning("NSE request failed after %d attempts: %s %s (last status: %s)",
                    retries + 1, url, params or "", last_status)
        raise RuntimeError(f"NSE request failed for {url} (last status: {last_status})")

    def _cached(self, key, fetch):
        """
        Return a fresh cached value for `key`, or call `fetch()` and cache it.

        Every symbol x expiry gets its own entry, so without a bound the cache
        would grow for as long as the server runs. Expired entries are dropped
        on each write, and the least recently used ones go once the cache is
        over `max_cache_entries`.
        """
        with self._lock:
            cached = self._cache.pop(key, None)
            if cached and time.time() - cached[0] < self.cache_ttl:
                self._cache[key] = cached  # re-insert: now the most recently used
                return cached[1]
        data = fetch()
        with self._lock:
            now = time.time()
            self._cache[key] = (now, data)
            for stale in [k for k, (stored_at, _) in self._cache.items() if now - stored_at >= self.cache_ttl]:
                del self._cache[stale]
            while len(self._cache) > self.max_cache_entries:
                del self._cache[next(iter(self._cache))]
        return data

    def get_expiries(self, symbol):
        """Live expiry dates (NSE 'DD-Mon-YYYY' strings, nearest first)."""
        symbol = symbol.upper()

        def fetch():
            info = self._get_json(
                f"{NSE_BASE}/api/option-chain-contract-info", params={"symbol": symbol}
            )
            return (info or {}).get("expiryDates") or []

        return self._cached(f"expiries:{symbol}", fetch)

    def get_option_chain(self, symbol, expiry=None, is_index=None):
        """
        Option chain for `symbol`, normalised to the classic shape:
          {"records": {"underlyingValue", "expiryDates", "data": [
              {"expiryDate", "strikePrice", "CE": {...}, "PE": {...}}, ...]}}
        `expiry` defaults to the nearest one.
        """
        symbol = symbol.upper()
        if is_index is None:
            is_index = symbol in INDEX_SYMBOLS

        expiries = []
        v3_error = None
        try:
            expiries = self.get_expiries(symbol)
        except RuntimeError as exc:
            v3_error = exc

        if expiries:
            expiry = expiry or expiries[0]

            def fetch_v3():
                return self._get_json(
                    f"{NSE_BASE}/api/option-chain-v3",
                    params={
                        "type": "Indices" if is_index else "Equity",
                        "symbol": symbol,
                        "expiry": expiry,
                    },
                )

            try:
                raw = self._cached(f"chain:{symbol}:{expiry}", fetch_v3)
                data = _normalise(raw, expiries)
                if data["records"]["data"]:
                    return data
            except RuntimeError as exc:
                v3_error = exc

        # Fallback: legacy endpoint (returns every expiry in one go).
        endpoint = "api/option-chain-indices" if is_index else "api/option-chain-equities"

        def fetch_legacy():
            return self._get_json(f"{NSE_BASE}/{endpoint}", params={"symbol": symbol})

        raw = self._cached(f"legacy:{symbol}", fetch_legacy)
        data = _normalise(raw, expiries)
        if not data["records"]["data"]:
            reason = f" ({v3_error})" if v3_error else ""
            raise RuntimeError(
                f"NSE returned an empty option chain for {symbol}{reason}. "
                "Check the symbol has F&O contracts, or NSE may be blocking this server's IP."
            )
        return data

    def get_quote(self, symbol, is_index=False):
        """Underlying spot price + basic quote info, independent of option chain."""
        symbol = symbol.upper()
        endpoint = "api/equity-stockIndices" if is_index else "api/quote-equity"
        params = {"index": symbol} if is_index else {"symbol": symbol}
        return self._get_json(f"{NSE_BASE}/{endpoint}", params=params)


def _normalise(raw, expiries=None):
    """Map v3 / legacy NSE payloads onto one shape the API layer can rely on."""
    records = (raw or {}).get("records") or {}
    rows = []
    spot = records.get("underlyingValue")
    for row in records.get("data") or []:
        ce, pe = row.get("CE"), row.get("PE")
        leg = ce or pe or {}
        # v3 names the per-row key "expiryDates" (plural); legacy used "expiryDate".
        expiry = row.get("expiryDate") or row.get("expiryDates") or leg.get("expiryDate")
        strike = row.get("strikePrice", leg.get("strikePrice"))
        if expiry is None or strike is None:
            continue
        if spot is None:
            spot = leg.get("underlyingValue")
        rows.append({"expiryDate": expiry, "strikePrice": strike, "CE": ce, "PE": pe})

    return {
        "records": {
            "underlyingValue": spot,
            "expiryDates": expiries or records.get("expiryDates") or [],
            "data": rows,
        }
    }


# Single shared client instance for the whole Flask process.
nse_client = NSEClient()
