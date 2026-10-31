/* Points at the Flask backend. Override before app.js loads if needed:
   <script>window.OPTIONS_API_BASE = "https://your-backend.example.com";</script> */
const API_BASE = (window.OPTIONS_API_BASE || 'http://localhost:5000').replace(/\/+$/, '');

// NSE retries can take a while, and a sleeping Render instance needs ~60s to
// wake, so data calls get a generous limit; the health check is short because
// the startup loop simply retries it.
const API_TIMEOUT_MS = 90000;
const HEALTH_TIMEOUT_MS = 10000;

/* GET a JSON endpoint. Always rejects with an Error whose message can be
   shown to the user as-is: the backend's own `error` text when it sent one,
   otherwise a plain description of what went wrong. */
async function apiGet(path, { timeout = API_TIMEOUT_MS } = {}){
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(), timeout);
  let res;
  try{
    res = await fetch(`${API_BASE}${path}`, { signal: controller.signal, headers: { Accept: 'application/json' } });
  }catch(err){
    if(err.name === 'AbortError'){
      throw new Error(`the backend took longer than ${Math.round(timeout/1000)}s to respond`);
    }
    // fetch() only throws like this for network-level failures (offline, DNS, CORS, server down).
    throw new Error(`could not reach the backend at ${API_BASE} — check your connection; if it was idle it may still be starting up`);
  }finally{
    clearTimeout(timer);
  }
  const body = await res.json().catch(()=>null);
  if(!res.ok){
    throw new Error((body && body.error) || `request failed (HTTP ${res.status})`);
  }
  if(body === null){
    throw new Error('the backend sent a response that is not JSON');
  }
  return body;
}

const Api = {
  health: () => apiGet('/api/health', { timeout: HEALTH_TIMEOUT_MS }),
  optionChain: (symbol, expiry) => apiGet(`/api/option-chain/${encodeURIComponent(symbol)}` + (expiry ? `?expiry=${encodeURIComponent(expiry)}` : '')),
  analyze: (symbol, params) => {
    const qs = new URLSearchParams(params).toString();
    return apiGet(`/api/analyze/${encodeURIComponent(symbol)}?${qs}`);
  }
};
