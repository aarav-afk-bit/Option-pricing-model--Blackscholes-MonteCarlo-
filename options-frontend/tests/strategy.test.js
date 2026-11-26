/* Strategy builder maths (js/strategy.js). Run: node --test 'options-frontend/tests/*.test.js' */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const read = (f)=> fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8');
const ctx = vm.createContext({ Math, Float64Array });
vm.runInContext(read('pricing.js'), ctx);
vm.runInContext(read('strategy.js'), ctx);   // no document: only the maths loads
const M = vm.runInContext('StrategyMath', ctx);

const leg = (side, type, strike, premium, qty = 1, iv = 0.2)=> ({ side, type, strike, premium, qty, iv });
const close = (a, b, tol = 1e-9)=> assert.ok(Math.abs(a - b) <= tol, `${a} vs ${b}`);

test('long straddle: pays both premiums, unlimited upside, two breakevens', () => {
  const legs = [leg('buy', 'call', 100, 5), leg('buy', 'put', 100, 5)];
  const a = M.analyse(legs);
  close(M.netPremium(legs), 10);
  close(a.maxLoss, -10);
  assert.equal(a.maxProfit, Infinity);
  assert.deepEqual([...a.breakevens], [90, 110]);
  close(M.pnlAtExpiry(legs, 80), 10);
});

test('bull call spread: capped profit and loss, one breakeven', () => {
  const legs = [leg('buy', 'call', 100, 6), leg('sell', 'call', 110, 2)];
  const a = M.analyse(legs);
  close(M.netPremium(legs), 4);
  close(a.maxProfit, 6);
  close(a.maxLoss, -4);
  assert.deepEqual([...a.breakevens], [104]);
});

test('iron condor: credit is the max profit, wings cap the loss', () => {
  const legs = [leg('sell', 'put', 95, 2), leg('buy', 'put', 90, 1), leg('sell', 'call', 105, 2), leg('buy', 'call', 110, 1)];
  const a = M.analyse(legs);
  close(M.netPremium(legs), -2);           // a credit
  close(a.maxProfit, 2);
  close(a.maxLoss, -3);
  assert.deepEqual([...a.breakevens], [93, 107]);
});

test('naked short call has unlimited loss; long put profit is capped at the strike', () => {
  assert.equal(M.analyse([leg('sell', 'call', 100, 4)]).maxLoss, -Infinity);
  const put = M.analyse([leg('buy', 'put', 100, 4)]);
  close(put.maxProfit, 96);
  close(put.maxLoss, -4);
  assert.deepEqual([...put.breakevens], [96]);
});

test('quantities scale everything', () => {
  const one = [leg('buy', 'call', 100, 6), leg('sell', 'call', 110, 2)];
  const two = one.map(l=> ({ ...l, qty: 2 }));
  close(M.analyse(two).maxProfit, 2 * M.analyse(one).maxProfit);
  close(M.netPremium(two), 2 * M.netPremium(one));
});

test('today\'s P&L tends to the expiry P&L as time runs out', () => {
  const legs = [leg('buy', 'call', 100, 5), leg('buy', 'put', 100, 5)];
  // At the money a sliver of time value (~0.4·S·σ·√T) remains, hence the ₹0.01 tolerance.
  for(const S of [85, 100, 120]) close(M.pnlToday(legs, S, 1e-8, 0.05, 0), M.pnlAtExpiry(legs, S), 0.01);
});

test('probability of profit matches a simulation of the terminal price', () => {
  const legs = [leg('buy', 'call', 100, 5), leg('buy', 'put', 100, 5)];
  const S = 100, T = 0.25, r = 0.05, q = 0, sigma = 0.25;
  const pop = M.probabilityOfProfit(legs, S, T, r, q, sigma);
  const samples = vm.runInContext(`sampleTerminalPrices(${S}, ${T}, ${r}, ${sigma}, ${q}, 200000)`, ctx);
  const simulated = samples.filter(x=> M.pnlAtExpiry(legs, x) > 0).length / samples.length;
  close(pop, simulated, 0.01);
});

test('net Greeks: a straddle is near delta-neutral with positive gamma and vega, negative theta', () => {
  const g = M.netGreeks([leg('buy', 'call', 100, 5), leg('buy', 'put', 100, 5)], 100, 0.25, 0.05, 0);
  assert.ok(Math.abs(g.delta) < 0.2 && g.gamma > 0 && g.vegaPer1 > 0 && g.thetaPerDay < 0);
});

test('every preset builds legs at chain strikes around the money', () => {
  for(const [id, preset] of Object.entries(M.PRESETS)){
    const legs = preset.legs(100, 5);
    assert.ok(legs.length >= 2, id);
    assert.ok(legs.every(([side, type, k])=> ['buy', 'sell'].includes(side) && ['call', 'put'].includes(type) && k >= 80 && k <= 120), id);
  }
});
