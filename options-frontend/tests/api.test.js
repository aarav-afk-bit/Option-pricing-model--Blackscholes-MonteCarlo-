/* Tests for js/api.js with fetch mocked. Run: node --test 'options-frontend/tests/*.test.js' */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'api.js'), 'utf8');

// Load api.js as the browser would (a classic script), with a fake fetch.
function loadApi(fakeFetch, base = 'https://backend.example.com/'){
  const ctx = vm.createContext({
    window: { OPTIONS_API_BASE: base }, fetch: fakeFetch, AbortController, URLSearchParams, setTimeout, clearTimeout,
  });
  return vm.runInContext(`${source}\n;({ Api, apiGet, API_BASE })`, ctx);
}

const jsonResponse = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

test('strips trailing slashes from the base URL and encodes the path', async () => {
  const calls = [];
  const { Api, API_BASE } = loadApi(async (url) => { calls.push(url); return jsonResponse(200, {}); });
  assert.equal(API_BASE, 'https://backend.example.com');
  await Api.optionChain('M&M', '30-Dec-2099');
  assert.equal(calls[0], 'https://backend.example.com/api/option-chain/M%26M?expiry=30-Dec-2099');
});

test('returns the parsed body on success', async () => {
  const { Api } = loadApi(async () => jsonResponse(200, { status: 'ok' }));
  assert.equal((await Api.health()).status, 'ok');
});

test("surfaces the backend's own error message", async () => {
  const { Api } = loadApi(async () => jsonResponse(404, { error: 'that strike/expiry is not in the live NSE chain' }));
  await assert.rejects(Api.analyze('NIFTY', { strike: 1 }), /not in the live NSE chain/);
});

test('falls back to the HTTP status when the error body is not JSON', async () => {
  const { Api } = loadApi(async () => ({ ok: false, status: 503, json: async () => { throw new SyntaxError('html'); } }));
  await assert.rejects(Api.health(), /request failed \(HTTP 503\)/);
});

test('explains network failures instead of "Failed to fetch"', async () => {
  const { Api } = loadApi(async () => { throw new TypeError('Failed to fetch'); });
  await assert.rejects(Api.health(), /could not reach the backend at https:\/\/backend\.example\.com/);
});

test('times out a request that never answers', async () => {
  const neverAnswers = (url, { signal }) => new Promise((_, reject) => {
    signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
  });
  const { apiGet } = loadApi(neverAnswers);
  await assert.rejects(apiGet('/api/slow', { timeout: 30 }), /took longer than 0s to respond/);
});
