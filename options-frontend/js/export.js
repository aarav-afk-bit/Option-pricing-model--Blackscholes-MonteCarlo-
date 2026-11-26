/* Export the current contract's results as a CSV file: inputs, the live
   analysis, every Monte Carlo Lab model and the option chain for the
   selected expiry. Numbers are written raw (no ₹ or % signs) so a
   spreadsheet can calculate with them. */

/* ---------- Pure helpers (also unit-tested in node) ---------- */
const ExportCSV = (function(){
  function cell(value){
    if(value === null || value === undefined || (typeof value === 'number' && !isFinite(value))) return '';
    if(typeof value === 'number') return String(value);
    let s = String(value);
    // Spreadsheets run text starting with = + - @ as a formula; neutralise it.
    if(/^[=+\-@\t\r]/.test(s) && isNaN(Number(s))) s = "'" + s;
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  const row = (values)=> values.map(cell).join(',');

  /* sections: [{ title, header?:[...], rows:[[...], ...] }] -> CSV text */
  function toCsv(sections){
    return sections.filter(s=>s.rows.length).map(s=>[
      row([s.title]),
      ...(s.header ? [row(s.header)] : []),
      ...s.rows.map(row),
    ].join('\r\n')).join('\r\n\r\n') + '\r\n';
  }

  /* Nested object -> [["a.b", value], ...] for the key/value sections. */
  function flatten(obj, prefix='', out=[]){
    Object.entries(obj || {}).forEach(([k, v])=>{
      const key = prefix ? `${prefix}.${k}` : k;
      if(v && typeof v === 'object' && !Array.isArray(v)) flatten(v, key, out);
      else if(Array.isArray(v)) out.push([key, v.join(' – ')]);
      else out.push([key, v]);
    });
    return out;
  }

  function fileName(symbol, strike, type, expiry, date){
    const side = type === 'put' ? 'PE' : 'CE';
    return [symbol || 'contract', strike ? `${strike}${side}` : '', expiry || '', date]
      .filter(Boolean).join('_').replace(/[^A-Za-z0-9_.-]/g, '-') + '.csv';
  }

  return { cell, row, toCsv, flatten, fileName };
})();

/* ---------- Page wiring ---------- */
if(typeof document !== 'undefined') (function(){
  const $ = (id)=> document.getElementById(id);
  let lastAnalysis = null, lastLab = null;

  // Keep the raw JSON of the latest live analysis (formatted page text loses precision).
  const originalAnalyze = Api.analyze;
  Api.analyze = async (...args)=>{
    const data = await originalAnalyze(...args);
    lastAnalysis = data;
    return data;
  };
  window.addEventListener('mc-lab:result', (e)=>{ lastLab = e.detail.data; });

  function num(id){
    const v = parseFloat($(id).value);
    return isNaN(v) ? null : v;
  }

  function buildSections(){
    const symbol = $('pSymbol').value.trim().toUpperCase();
    const type = $('btnPut').classList.contains('active') ? 'put' : 'call';
    const expiry = $('expirySelect').value;
    const strike = num('pStrike');
    const sections = [{ title:'Contract and inputs', header:['field', 'value'], rows:[
      ['symbol', symbol], ['option type', type], ['expiry', expiry], ['strike', strike],
      ['spot', num('pSpot')], ['days to expiry', num('pDays')], ['risk-free rate %', num('pRate')],
      ['volatility %', num('pVol')], ['dividend yield %', num('pDiv')], ['market premium (LTP)', num('pMarket')],
      ['exported at', new Date().toISOString()], ['source', location.href],
    ]}];

    // Only include the live analysis if it is for the contract on screen.
    if(lastAnalysis && lastAnalysis.symbol === symbol && lastAnalysis.strike === strike && lastAnalysis.optionType === type){
      const a = lastAnalysis;
      sections.push({ title:'Live analysis', header:['field', 'value'], rows:ExportCSV.flatten({
        fetchedAt:a.fetchedAt, inputs:a.inputs, market:a.market, blackScholes:a.blackScholes, greeks:a.greeks,
        crr:a.crr, monteCarlo:a.monteCarlo, impliedVolatility:a.impliedVolatility, liquidity:a.liquidity,
        suggestion:a.suggestion,
      }) });
    }

    if(lastLab && Math.abs(lastLab.inputs.strike - strike) < 1e-9 && lastLab.inputs.type === type){
      const rows = [['Black-Scholes (formula)', lastLab.blackScholes.price, '', '', '', '', '']];
      Object.values(lastLab.models).forEach(m=> rows.push([
        m.label, m.price, m.stdError, m.ci95 ? m.ci95[0] : '', m.ci95 ? m.ci95[1] : '', m.paths, m.formulaPrice ?? '',
      ]));
      sections.push({ title:'Monte Carlo Lab', header:['model', 'price', 'std error', '95% low', '95% high', 'paths', 'formula / tree check'], rows });
    }

    const legs = currentChain && currentChain.chain && currentChain.chain[expiry];
    if(legs){
      const rows = Object.keys(legs).map(Number).sort((a, b)=> a - b).map(k=>{
        const c = legs[k].CE || {}, p = legs[k].PE || {};
        return [k, c.lastPrice, c.impliedVolatility, c.openInterest, c.changeInOpenInterest, c.bid, c.ask,
                p.lastPrice, p.impliedVolatility, p.openInterest, p.changeInOpenInterest, p.bid, p.ask];
      });
      sections.push({ title:`Option chain ${expiry} (spot ${currentChain.spot})`, rows, header:[
        'strike', 'CE LTP', 'CE IV %', 'CE OI', 'CE chg OI', 'CE bid', 'CE ask',
        'PE LTP', 'PE IV %', 'PE OI', 'PE chg OI', 'PE bid', 'PE ask'] });
    }
    return { sections, name:ExportCSV.fileName(symbol, strike, type, expiry, new Date().toISOString().slice(0, 10)) };
  }

  function download(){
    const { sections, name } = buildSections();
    // The BOM makes Excel read the file as UTF-8.
    const blob = new Blob(['﻿' + ExportCSV.toCsv(sections)], { type:'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(()=> URL.revokeObjectURL(a.href), 1000);
  }

  $('exportCsvBtn').addEventListener('click', download);
  window.ExportResults = { buildSections };
})();
