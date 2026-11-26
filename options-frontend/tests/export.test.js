/* Tests for js/export.js's CSV helpers. Run: node --test 'options-frontend/tests/*.test.js' */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'export.js'), 'utf8');
const E = vm.runInNewContext(`${source}\n;ExportCSV`, {});   // no document: only the helpers load

test('numbers are written raw and empty values stay empty', () => {
  assert.equal(E.row([24500, -0.3516, 0, null, undefined, NaN]), '24500,-0.3516,0,,,');
});

test('text with commas, quotes or newlines is quoted', () => {
  assert.equal(E.cell('BUY CALL — UNDERVALUED'), 'BUY CALL — UNDERVALUED');
  assert.equal(E.cell('a, b'), '"a, b"');
  assert.equal(E.cell('say "hi"'), '"say ""hi"""');
  assert.equal(E.cell('line1\nline2'), '"line1\nline2"');
});

test('formula-like text is neutralised but negative numbers are not', () => {
  assert.equal(E.cell('=HYPERLINK("x")'), '"\'=HYPERLINK(""x"")"');
  assert.equal(E.cell('@SUM(A1)'), "'@SUM(A1)");
  assert.equal(E.cell('-12.5'), '-12.5');
  assert.equal(E.cell(-12.5), '-12.5');
});

test('sections become titled blocks separated by blank lines', () => {
  const csv = E.toCsv([
    { title:'Inputs', header:['field', 'value'], rows:[['spot', 100]] },
    { title:'Empty', rows:[] },
    { title:'Chain', rows:[[1, 2]] },
  ]);
  assert.equal(csv, 'Inputs\r\nfield,value\r\nspot,100\r\n\r\nChain\r\n1,2\r\n');
});

test('nested results flatten to dotted keys', () => {
  // Compare as JSON: arrays built inside the VM have that context's Array prototype.
  assert.equal(JSON.stringify(E.flatten({ greeks:{ gamma:0.01 }, crr:{ european:5 }, ci:[1, 2], note:'x' })),
    JSON.stringify([['greeks.gamma', 0.01], ['crr.european', 5], ['ci', '1 – 2'], ['note', 'x']]));
});

test('file names are safe and descriptive', () => {
  assert.equal(E.fileName('NIFTY', 24800, 'put', '27-Jan-2027', '2026-11-22'), 'NIFTY_24800PE_27-Jan-2027_2026-11-22.csv');
  assert.equal(E.fileName('M&M', 3000, 'call', '', '2026-11-22'), 'M-M_3000CE_2026-11-22.csv');
});
