/* Mispricing scanner maths (js/scanner.js). Run: node --test 'options-frontend/tests/*.test.js' */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const read = (f)=> fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8');
const ctx = vm.createContext({ Math, Float64Array });
vm.runInContext(read('pricing.js'), ctx);
vm.runInContext(read('scanner.js'), ctx);   // no document: only the maths loads
const M = vm.runInContext('ScannerMath', ctx);
const bs = vm.runInContext('blackScholes', ctx);

const S = 24500, T = 30 / 365, r = 0.065, q = 0;
const F = S * Math.exp(r * T);
const trueIv = (K)=>{ const x = Math.log(K / F); return 0.14 - 0.25 * x + 2.0 * x * x; };   // a skewed smile

/* A chain priced exactly on the smile, with bid/ask 1% around the price. */
function chain(mispriced = {}){
  const rows = [];
  for(let K = 22500; K <= 26500; K += 250){
    const iv = trueIv(K), p = bs(S, K, T, r, iv, q);
    const leg = (price, k)=> { const px = price * (mispriced[k] ?? 1);
      return { lastPrice: px, bid: px * 0.995, ask: px * 1.005, impliedVolatility: iv * 100, openInterest: 1000 }; };
    rows.push({ strike: K, CE: leg(p.call, `${K}C`), PE: leg(p.put, `${K}P`) });
  }
  return rows;
}

test('fitSmile recovers a quadratic exactly', () => {
  const pts = [-0.1, -0.05, 0, 0.05, 0.1].map(x=>({ x, y: 0.2 - 0.3 * x + 1.5 * x * x }));
  const f = M.fitSmile(pts);
  for(const x of [-0.08, 0, 0.07]) assert.ok(Math.abs(f(x) - (0.2 - 0.3 * x + 1.5 * x * x)) < 1e-12);
  assert.equal(M.fitSmile(pts.slice(0, 3)), null);   // too few points
});

test('a chain priced on the smile shows no meaningful gaps', () => {
  const { results } = M.scan(chain(), S, T, r, q);
  assert.ok(results.length >= 12);
  assert.ok(results.every(x=> Math.abs(x.gapPct) < 1), JSON.stringify(results.map(x=>x.gapPct)));
});

test('a cheap and a rich option are ranked first and last', () => {
  const { results } = M.scan(chain({ '23750P': 0.85, '25250C': 1.2 }), S, T, r, q);
  const first = results[0], last = results[results.length - 1];
  assert.equal(`${first.strike}${first.type}`, '23750put');
  assert.ok(first.gapPct < -10);
  assert.equal(`${last.strike}${last.type}`, '25250call');
  assert.ok(last.gapPct > 15);
});

test('only out-of-the-money options are scanned', () => {
  const { results } = M.scan(chain(), S, T, r, q);
  assert.ok(results.every(x=> x.type === (x.strike >= S ? 'call' : 'put')));
});

test('illiquid quotes are skipped: tiny prices and wide spreads', () => {
  const rows = chain();
  rows.find(r_=> r_.strike === 25000).CE = { lastPrice: 120, bid: 80, ask: 160, impliedVolatility: 14 };  // 67% spread
  const { results } = M.scan(rows, S, T, r, q);
  assert.ok(!results.some(x=> x.strike === 25000));
  assert.ok(results.every(x=> x.price >= 1));
});

test('market price uses the mid when quoted, else the last price', () => {
  assert.deepEqual({ ...M.marketPrice({ bid: 99, ask: 101, lastPrice: 90 }) }, { price: 100, spreadPct: 2 });
  assert.deepEqual({ ...M.marketPrice({ bid: 0, ask: 0, lastPrice: 90 }) }, { price: 90, spreadPct: null });
});
