/* js/pricing.js must agree with the Python engine (options-backend/pricing.py).
   Reference values come from tests/fixtures/pricing_cases.json, which the
   backend test suite keeps in sync with pricing.py.
   Run: node --test 'options-frontend/tests/*.test.js' */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'pricing.js'), 'utf8');
const P = vm.runInNewContext(`${source}\n;({ blackScholes, bsGreeks, crrPrice, impliedVol })`, { Math, Float64Array });
const { crrSteps, cases } = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'pricing_cases.json'), 'utf8'));

/* The JS normal CDF uses the Abramowitz-Stegun erf approximation (max error
   ~1.5e-7), so prices and Greeks can differ from scipy by that much times the
   size of S or K. Allow 3e-7 x max(S, K) — e.g. ₹0.007 on a ₹24,500 index. */
function close(actual, expected, scale, label){
  const tol = 3e-7 * scale + 1e-12;
  assert.ok(Math.abs(actual - expected) <= tol, `${label}: JS ${actual} vs Python ${expected} (tolerance ${tol})`);
}

const label = ({S, K, T, sigma, q}) => `S=${S} K=${K} T=${T.toFixed(4)} σ=${sigma} q=${q}`;

test(`Black-Scholes prices match Python (${cases.length} contracts)`, () => {
  for(const c of cases){
    const {S, K, T, r, sigma, q} = c.inputs;
    const bs = P.blackScholes(S, K, T, r, sigma, q);
    close(bs.call, c.blackScholes.call, Math.max(S, K), `${label(c.inputs)} call`);
    close(bs.put, c.blackScholes.put, Math.max(S, K), `${label(c.inputs)} put`);
    close(bs.d1, c.blackScholes.d1, 1, `${label(c.inputs)} d1`);
  }
});

test('every Greek matches Python', () => {
  for(const c of cases){
    const {S, K, T, r, sigma, q} = c.inputs;
    const gk = P.bsGreeks(S, K, T, r, sigma, q);
    for(const [key, expected] of Object.entries(c.greeks)){
      assert.ok(key in gk, `pricing.js bsGreeks() is missing "${key}"`);
      close(gk[key], expected, Math.max(S, K), `${label(c.inputs)} ${key}`);
    }
  }
});

test(`CRR binomial (${crrSteps} steps) matches Python`, () => {
  for(const c of cases){
    const {S, K, T, r, sigma, q} = c.inputs;
    for(const [key, expected] of Object.entries(c.crr)){
      const [side, style] = key.split('_');
      const js = P.crrPrice(S, K, T, r, sigma, q, crrSteps, side, style === 'american');
      // Same algorithm, no approximations: should agree to floating-point noise.
      assert.ok(Math.abs(js - expected) <= 1e-9 * Math.max(S, K), `${label(c.inputs)} ${key}: JS ${js} vs Python ${expected}`);
    }
  }
});

test('implied volatility recovers the volatility behind each fixture price', () => {
  for(const c of cases){
    const {S, K, T, r, sigma, q} = c.inputs;
    // A price error e moves the solved IV by about e / vega, so contracts whose
    // price barely depends on vol (deep ITM/OTM, days to expiry) get a looser bound.
    const ivTol = (3e-7 * Math.max(S, K)) / c.greeks.vega + 1e-4;
    for(const side of ['call', 'put']){
      const iv = P.impliedVol(c.blackScholes[side], S, K, T, r, q, side);
      if(Number.isNaN(iv)) continue;   // price indistinguishable from its bound: no vol to recover
      assert.ok(Math.abs(iv - sigma) < ivTol, `${label(c.inputs)} ${side}: IV ${iv} vs ${sigma} (tolerance ${ivTol})`);
    }
  }
});
