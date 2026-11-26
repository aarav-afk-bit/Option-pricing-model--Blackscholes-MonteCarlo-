/* Mispricing scanner: for the selected expiry, fit a smooth volatility smile
   through the whole chain, price every strike off that smile, and rank the
   options whose market price strays furthest from it. A relative-value view:
   each option is compared with its neighbours, not with one flat volatility. */

/* ---------- Pure maths ---------- */
const ScannerMath = (function(){
  /* Weighted least squares fit of iv = a + b x + c x^2, with x = ln(K / forward). */
  function fitSmile(points){
    if(points.length < 4) return null;
    const S = Array(5).fill(0), Y = Array(3).fill(0);
    points.forEach(({ x, y, w = 1 })=>{
      for(let p = 0; p < 5; p++) S[p] += w * x ** p;
      for(let p = 0; p < 3; p++) Y[p] += w * y * x ** p;
    });
    // Normal equations, solved by Cramer's rule (3x3).
    const m = [[S[0], S[1], S[2]], [S[1], S[2], S[3]], [S[2], S[3], S[4]]];
    const det = (a)=> a[0][0]*(a[1][1]*a[2][2]-a[1][2]*a[2][1]) - a[0][1]*(a[1][0]*a[2][2]-a[1][2]*a[2][0]) + a[0][2]*(a[1][0]*a[2][1]-a[1][1]*a[2][0]);
    const d = det(m);
    if(Math.abs(d) < 1e-18) return null;
    const coef = [0, 1, 2].map(col=> det(m.map((row, i)=> row.map((v, j)=> j === col ? Y[i] : v))) / d);
    return (x)=> coef[0] + coef[1] * x + coef[2] * x * x;
  }

  /* Market price of one leg: bid/ask mid when quoted, else last price. Also the spread as a % of mid. */
  function marketPrice(leg){
    if(leg.bid > 0 && leg.ask >= leg.bid){
      const mid = (leg.bid + leg.ask) / 2;
      return { price: mid, spreadPct: (leg.ask - leg.bid) / mid * 100 };
    }
    return { price: leg.lastPrice || 0, spreadPct: null };
  }

  /* rows: [{ strike, CE:{lastPrice, bid, ask, impliedVolatility, openInterest}, PE:{...} }]
     Returns every liquid out-of-the-money option with its smile-fair price and gap, cheapest first. */
  function scan(rows, S, T, r, q, opts = {}){
    const minPrice = opts.minPrice ?? 1, maxSpreadPct = opts.maxSpreadPct ?? 30;
    const forward = S * Math.exp((r - q) * T);
    // Out-of-the-money options carry the cleanest volatility information.
    const quotes = rows.map(row=>{
      const type = row.strike >= S ? 'call' : 'put';
      const leg = row[type === 'call' ? 'CE' : 'PE'];
      if(!leg) return null;
      const { price, spreadPct } = marketPrice(leg);
      return { strike: row.strike, type, price, spreadPct, iv: (leg.impliedVolatility || 0) / 100, oi: leg.openInterest || 0 };
    }).filter(q=> q && q.price >= minPrice && (q.spreadPct == null || q.spreadPct <= maxSpreadPct));

    const smile = fitSmile(quotes.filter(q=> q.iv > 0).map(q=>({ x: Math.log(q.strike / forward), y: q.iv, w: Math.sqrt(q.price) })));
    if(!smile) return { smile: null, results: [] };

    const results = quotes.map(qt=>{
      const fairIv = Math.max(smile(Math.log(qt.strike / forward)), 0.01);
      const bs = blackScholes(S, qt.strike, T, r, fairIv, q);
      const fair = qt.type === 'call' ? bs.call : bs.put;
      return { ...qt, fairIv, fair, gap: qt.price - fair, gapPct: (qt.price - fair) / fair * 100 };
    }).filter(x=> x.fair >= minPrice / 2).sort((a, b)=> a.gapPct - b.gapPct);
    return { smile, results };
  }

  return { fitSmile, marketPrice, scan };
})();

/* ---------- Page wiring ---------- */
if(typeof document !== 'undefined') (function(){
  const $ = (id)=> document.getElementById(id);
  const rupees = (v)=> (v < 0 ? '−' : '') + '₹' + Math.abs(v).toLocaleString('en-IN', { minimumFractionDigits:2, maximumFractionDigits:2 });
  let lastExpiry = null;

  function inputs(){
    const expiry = $('expirySelect').value;
    const legs = currentChain && currentChain.chain && currentChain.chain[expiry];
    if(!legs) return null;
    return {
      expiry,
      rows: Object.keys(legs).map(k=>({ strike: Number(k), CE: legs[k].CE, PE: legs[k].PE })).sort((a, b)=> a.strike - b.strike),
      S: currentChain.spot,
      T: (daysToExpiry(expiry) || 1) / 365,
      r: (parseFloat($('pRate').value) || 6.5) / 100,
      q: (parseFloat($('pDiv').value) || 0) / 100,
    };
  }

  function row(x){
    const cls = x.gapPct < 0 ? 'cheap' : 'rich';
    return `<tr data-strike="${x.strike}" data-type="${x.type}" title="Click to analyse this option">
      <td>${x.strike.toLocaleString('en-IN')} ${x.type === 'call' ? 'CE' : 'PE'}</td>
      <td>${rupees(x.price)}</td><td>${rupees(x.fair)}</td>
      <td class="${cls}">${x.gapPct >= 0 ? '+' : ''}${x.gapPct.toFixed(1)}%</td>
      <td>${(x.iv * 100).toFixed(1)}% / ${(x.fairIv * 100).toFixed(1)}%</td>
      <td>${x.spreadPct == null ? 'LTP' : x.spreadPct.toFixed(1) + '%'}</td>
    </tr>`;
  }

  function render(){
    const inp = inputs();
    const body = $('scanBody');
    if(!inp){ body.innerHTML = '<div class="scan-empty">Load a symbol to scan its option chain.</div>'; return; }
    lastExpiry = inp.expiry;
    const { results } = ScannerMath.scan(inp.rows, inp.S, inp.T, inp.r, inp.q);
    if(results.length < 4){
      body.innerHTML = '<div class="scan-empty">Not enough liquid out-of-the-money quotes in this expiry to fit a smile.</div>';
      return;
    }
    const n = Math.min(5, Math.floor(results.length / 2));
    const cheap = results.slice(0, n).filter(x=> x.gapPct < 0);
    const rich = results.slice(-n).reverse().filter(x=> x.gapPct > 0);
    const head = '<thead><tr><th>Option</th><th>Market</th><th>Smile fair</th><th>Gap</th><th>IV mkt / fit</th><th>Spread</th></tr></thead>';
    const table = (title, list, note)=> `<div class="scan-block"><div class="scan-title">${title}</div>` +
      (list.length ? `<table class="scan-table">${head}<tbody>${list.map(row).join('')}</tbody></table>` : `<div class="scan-empty">${note}</div>`) + '</div>';
    body.innerHTML = table('Cheapest vs the smile', cheap, 'No option trades below the fitted smile.') +
      table('Richest vs the smile', rich, 'No option trades above the fitted smile.') +
      `<div class="scan-note">Scanned ${results.length} liquid out-of-the-money options in ${inp.expiry} (price ≥ ₹1, spread ≤ 30%). ` +
      `"Smile fair" prices each strike at the volatility a smooth curve fitted through the whole chain gives it, so a large gap means the ` +
      `option is out of line with its neighbours — or its quote is stale. Click a row to analyse it. Not investment advice.</div>`;
  }

  // Clicking a result loads that option into the dashboard's controls.
  $('scanBody').addEventListener('click', (e)=>{
    const tr = e.target.closest('tr[data-strike]');
    if(!tr) return;
    const sel = $('strikeSelect');
    sel.value = tr.dataset.strike;
    sel.dispatchEvent(new Event('change'));
    $(tr.dataset.type === 'put' ? 'btnPut' : 'btnCall').click();
    $('fetchBtn').click();
    sel.scrollIntoView({ behavior:'smooth', block:'center' });
  });

  new MutationObserver(()=>{ if(/^LIVE CHAIN LOADED/.test($('statusText').textContent)) render(); })
    .observe($('statusText'), { childList:true, characterData:true, subtree:true });
  $('expirySelect').addEventListener('change', ()=> setTimeout(()=>{ if($('expirySelect').value !== lastExpiry) render(); }, 0));
  $('scanRefresh').addEventListener('click', render);
})();
