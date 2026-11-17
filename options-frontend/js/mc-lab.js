/* Monte Carlo Lab: prices the contract in the input strip by simulation
   (via /api/montecarlo) and shows each model next to Black-Scholes and the
   market price. Self-contained: it reads the dashboard's inputs and watches
   the status line to re-run after each analysis, so app.js needs no hooks. */
(function(){
  const $ = (id)=> document.getElementById(id);
  const rupees = (v, dec=2)=> (v==null || !isFinite(v)) ? '—' : '₹'+Number(v).toLocaleString('en-IN',{minimumFractionDigits:dec, maximumFractionDigits:dec});
  const signed = (v)=> (v==null || !isFinite(v)) ? '—' : (v>=0 ? '+' : '−') + rupees(Math.abs(v));
  const esc = (s)=> String(s).replace(/[&<>"]/g, (c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  let lastRun = 0;

  /* Contract from the input strip, or null with a reason. */
  function readInputs(){
    const num = (id)=> parseFloat($(id).value);
    const inputs = {
      spot:num('pSpot'), strike:num('pStrike'), days:num('pDays'),
      rate:num('pRate'), div:num('pDiv'), vol:num('pVol'),
      type: $('btnPut').classList.contains('active') ? 'put' : 'call',
    };
    for(const k of ['spot','strike','days','vol']){
      if(!(inputs[k] > 0)) return { error:`Needs ${k === 'vol' ? 'volatility' : k} in the input strip — fetch live data first.` };
    }
    if(isNaN(inputs.rate)) inputs.rate = 6.5;
    if(isNaN(inputs.div)) inputs.div = 0;
    // Optional model settings: only filled-in fields are sent; the server defaults the rest.
    document.querySelectorAll('#mcSettings [data-param]').forEach(el=>{
      if(el.value.trim() !== '') inputs[el.dataset.param] = el.value.trim();
    });
    return { inputs, market: num('pMarket') || null };
  }

  function card(cls, name, price, lines, desc){
    return `<div class="mc-model ${cls}">
      <span class="name">${esc(name)}</span>
      <span class="px">${rupees(price)}</span>
      ${lines.join('')}
      ${desc ? `<span class="desc">${esc(desc)}</span>` : ''}
    </div>`;
  }

  function modelCard(m, bsPrice){
    const diff = m.price - bsPrice;
    // Within the 95% interval of the simulation = statistically the same price.
    const agrees = Math.abs(diff) <= 1.96 * m.stdError + 1e-9;
    const lines = [
      `<span class="ci">95%: ${rupees(m.ci95[0])} – ${rupees(m.ci95[1])}</span>`,
      `<span class="diff ${agrees ? 'agree' : 'differ'}">${signed(diff)} vs Black-Scholes${agrees ? ' · agrees' : ''}</span>`,
      `<span class="meta">${m.paths.toLocaleString('en-IN')} paths${m.efficiencyGain ? ` · ${m.efficiencyGain.toFixed(0)}× fewer paths than plain MC` : ''}</span>`,
    ];
    if(m.formulaPrice != null){
      lines.push(`<span class="meta">${esc(m.checkLabel || 'Formula check')}: ${rupees(m.formulaPrice)}</span>`);
    }
    if(m.earlyExercisePremium != null){
      lines.push(`<span class="meta">Early-exercise premium ${rupees(m.earlyExercisePremium)} · exercised early on ${(m.exerciseShare*100).toFixed(0)}% of paths</span>`);
    }
    return card('', m.label, m.price, lines, m.description);
  }

  function render(data, market){
    const bsPrice = data.blackScholes.price;
    const cards = [card('bs', 'Black-Scholes (formula)', bsPrice,
      [`<span class="meta">σ ${(data.inputs.vol*100).toFixed(2)}% · ${data.inputs.days} days</span>`],
      'Closed-form price: constant volatility, log-normal returns.')];
    // JSON object keys arrive sorted alphabetically; show models in a deliberate order.
    const ORDER = ['gbm', 'heston', 'jumps', 'american'];
    Object.keys(data.models)
      .sort((a, b)=> (ORDER.indexOf(a)+1 || 99) - (ORDER.indexOf(b)+1 || 99))
      .forEach(id=> cards.push(modelCard(data.models[id], bsPrice)));
    if(market){
      cards.push(card('market', 'Market (LTP)', market,
        [`<span class="meta">${signed(market-bsPrice)} vs Black-Scholes</span>`],
        'What the option actually trades at on NSE.'));
    }
    $('mcCompare').innerHTML = cards.join('');
  }

  /* Shared look for the lab's charts (kept local so the lab doesn't depend on app.js). */
  const charts = {};
  const TICK = { color:'#5c5d54', font:{ family:'JetBrains Mono', size:9.5 } };
  const GRID = { color:'#1d1e18' };
  const axisTitle = (text)=> ({ display:true, text, color:'#7d7e72', font:{ family:'JetBrains Mono', size:9.5 } });
  function drawChart(id, config){
    if(!window.Chart) return;
    if(charts[id]) charts[id].destroy();
    charts[id] = new Chart($(id).getContext('2d'), config);
  }
  const LEGEND = { labels:{ color:'#9b9c8f', font:{ family:'JetBrains Mono', size:10 }, boxWidth:12,
    filter:(item)=> !item.text.startsWith('_') } };   // "_..." datasets are band edges, not legend entries
  const TOOLTIP = { backgroundColor:'#16170f', borderColor:'#282a22', borderWidth:1, titleColor:'#ffb020',
    bodyColor:'#eae7dc', titleFont:{ family:'JetBrains Mono' }, bodyFont:{ family:'JetBrains Mono', size:11 } };

  /* Running estimate vs paths for plain and variance-reduced Monte Carlo,
     each with its 95% band, against the Black-Scholes price. */
  function renderConvergence(data){
    const conv = data.convergence || [];
    if(!conv.length) return;
    const bs = data.blackScholes.price;
    const pts = (key, f)=> conv.map(c=>({ x:c.paths, y:f(c[key]) }));
    const band = (key, color, fill)=> [
      { label:`_${key} hi`, data:pts(key, v=>v.price + 1.96*v.stdError), borderWidth:0, pointRadius:0, fill:false },
      { label:`_${key} lo`, data:pts(key, v=>v.price - 1.96*v.stdError), borderWidth:0, pointRadius:0, backgroundColor:fill, fill:'-1' },
    ];
    drawChart('mcConvergence', {
      type:'line',
      data:{ datasets:[
        ...band('plain', null, 'rgba(155,156,143,0.15)'),
        { label:'Plain Monte Carlo', data:pts('plain', v=>v.price), borderColor:'#9b9c8f', borderWidth:1.5, pointRadius:2 },
        ...band('reduced', null, 'rgba(255,176,32,0.25)'),
        { label:'Lab engine (variance-reduced)', data:pts('reduced', v=>v.price), borderColor:'#ffb020', borderWidth:2, pointRadius:2 },
        { label:'Black-Scholes', data:[{x:conv[0].paths, y:bs}, {x:conv[conv.length-1].paths, y:bs}], borderColor:'#7fd4ff', borderDash:[5,4], borderWidth:1.5, pointRadius:0 },
      ]},
      options:{
        responsive:true, maintainAspectRatio:false, animation:false,
        interaction:{ mode:'nearest', intersect:false },
        plugins:{ legend:LEGEND, tooltip:{ ...TOOLTIP, filter:(i)=> !i.dataset.label.startsWith('_'),
          callbacks:{ title:(it)=> it.length ? `${it[0].parsed.x.toLocaleString('en-IN')} paths` : '',
                      label:(c)=> `${c.dataset.label}: ${rupees(c.parsed.y)}` } } },
        scales:{
          x:{ type:'logarithmic', ticks:{ ...TICK, maxRotation:0, callback:(v)=> [1e3,1e4,1e5,2e5,5e4,5e3].includes(v) ? v.toLocaleString('en-IN') : '' }, grid:GRID, title:axisTitle('Simulated paths (log scale)') },
          y:{ ticks:{ ...TICK, callback:(v)=> '₹'+Number(v).toLocaleString('en-IN') }, grid:GRID, title:axisTitle('Price estimate') },
        },
      },
    });
    const last = conv[conv.length-1];
    const ratio = last.plain.stdError / last.reduced.stdError;
    $('mcConvergenceFoot').textContent =
      `Shaded bands are 95% intervals. At ${last.paths.toLocaleString('en-IN')} paths the lab engine's band is ${ratio.toFixed(1)}× narrower ` +
      `than plain Monte Carlo — plain MC would need about ${Math.round(ratio*ratio)}× as many paths to match it.`;
  }

  /* Fan of simulated price paths: 5-95% and 25-75% bands, median, a few
     example paths and the strike, over the days to expiry. */
  let lastData = null;
  function renderFan(data){
    lastData = data;
    const fan = (data.fans || {})[$('mcFanModel').value];
    if(!fan) return;
    const xy = (arr)=> arr.map((y, i)=>({ x:fan.days[i], y }));
    const K = data.inputs.strike;
    const datasets = fan.samples.map((path, i)=>({
      label:'_sample'+i, data:xy(path), borderColor:'rgba(155,156,143,0.18)', borderWidth:1, pointRadius:0,
    }));
    datasets.push(
      { label:'_p95', data:xy(fan.p95), borderWidth:0, pointRadius:0, fill:false },
      { label:'5–95% of paths', data:xy(fan.p5), borderWidth:0, pointRadius:0, backgroundColor:'rgba(255,176,32,0.10)', fill:'-1' },
      { label:'_p75', data:xy(fan.p75), borderWidth:0, pointRadius:0, fill:false },
      { label:'25–75% of paths', data:xy(fan.p25), borderWidth:0, pointRadius:0, backgroundColor:'rgba(255,176,32,0.22)', fill:'-1' },
      { label:'Median path', data:xy(fan.p50), borderColor:'#ffb020', borderWidth:2, pointRadius:0 },
      { label:'Strike', data:[{x:0, y:K}, {x:fan.days[fan.days.length-1], y:K}], borderColor:'#7fd4ff', borderDash:[5,4], borderWidth:1.5, pointRadius:0 },
    );
    drawChart('mcFan', {
      type:'line', data:{ datasets },
      options:{
        responsive:true, maintainAspectRatio:false, animation:false,
        interaction:{ mode:'nearest', intersect:false },
        plugins:{ legend:LEGEND, tooltip:{ ...TOOLTIP, filter:(i)=> !i.dataset.label.startsWith('_'),
          callbacks:{ title:(it)=> it.length ? `Day ${it[0].parsed.x.toFixed(0)}` : '',
                      label:(c)=> `${c.dataset.label}: ${rupees(c.parsed.y, 0)}` } } },
        scales:{
          x:{ type:'linear', min:0, max:fan.days[fan.days.length-1], ticks:{ ...TICK, maxRotation:0 }, grid:GRID, title:axisTitle('Days from today') },
          y:{ ticks:{ ...TICK, callback:(v)=> Number(v).toLocaleString('en-IN') }, grid:GRID, title:axisTitle('Underlying price') },
        },
      },
    });
    const side = data.inputs.type === 'call' ? 'above' : 'below';
    $('mcFanFoot').textContent =
      `${(fan.finalItmShare*100).toFixed(1)}% of simulated paths finish ${side} the strike of ${rupees(K, 0)} (in the money). ` +
      `Half of them end between ${rupees(fan.p25[fan.p25.length-1], 0)} and ${rupees(fan.p75[fan.p75.length-1], 0)}.`;
  }

  /* ---------- Calibration to the live chain ---------- */
  const FIT_STYLE = {
    blackScholes: { name:'Black-Scholes (one vol)', color:'#7fd4ff', dash:[5,4] },
    heston:       { name:'Heston', color:'#ffb020', dash:[] },
    jumps:        { name:'Merton jumps', color:'#c792ea', dash:[] },
  };
  let lastCalibration = null;

  function renderCalibration(cal){
    lastCalibration = cal;
    const T = cal.days / 365;
    $('mcCalib').hidden = false;
    $('mcCalibTitle').textContent = `${cal.symbol} ${cal.expiry} · ${cal.quotes.length} strikes · ${cal.elapsedMs.toFixed(0)} ms`;
    $('mcCalibTable').innerHTML = '<tr><th>Model</th><th>Avg miss</th><th>Avg ₹ miss</th></tr>' +
      Object.keys(FIT_STYLE).map(id=>{
        const f = cal.fits[id];
        return `<tr class="${cal.best===id ? 'best' : ''}"><td>${FIT_STYLE[id].name}</td>` +
          `<td>${f.rmseVolPts.toFixed(2)} vol pts</td><td>${rupees(f.rmseRupees)}</td></tr>`;
      }).join('');

    // Plot implied vols: market dots vs each fitted model's smile.
    const ivOf = (price, q)=> impliedVol(price, cal.spot, q.strike, T, cal.rate, cal.div, q.type) * 100;
    const datasets = [{ label:'Market', data:cal.quotes.map(q=>({ x:q.strike, y:q.iv*100 })), type:'scatter',
      backgroundColor:'#eae7dc', pointRadius:3.5 }];
    Object.keys(FIT_STYLE).forEach(id=>{
      const s = FIT_STYLE[id];
      datasets.push({ label:s.name, data:cal.fits[id].prices.map((p, i)=>({ x:cal.quotes[i].strike, y:ivOf(p, cal.quotes[i]) }))
        .filter(pt=>isFinite(pt.y)), borderColor:s.color, borderDash:s.dash, borderWidth:2, pointRadius:0, tension:0.3 });
    });
    datasets.push({ label:'_spot', data:[{x:cal.spot, y:Math.min(...cal.quotes.map(q=>q.iv*100))}, {x:cal.spot, y:Math.max(...cal.quotes.map(q=>q.iv*100))}],
      borderColor:'rgba(155,156,143,0.5)', borderDash:[2,3], borderWidth:1, pointRadius:0 });
    drawChart('mcSmileFit', {
      type:'line', data:{ datasets },
      options:{
        responsive:true, maintainAspectRatio:false, animation:false,
        interaction:{ mode:'nearest', intersect:false },
        plugins:{ legend:LEGEND, tooltip:{ ...TOOLTIP, filter:(i)=> !i.dataset.label.startsWith('_'),
          callbacks:{ title:(it)=> it.length ? `Strike ${it[0].parsed.x.toLocaleString('en-IN')}` : '',
                      label:(c)=> `${c.dataset.label}: ${c.parsed.y.toFixed(2)}%` } } },
        scales:{
          x:{ type:'linear', ticks:{ ...TICK, maxRotation:0, callback:(v)=> Number(v).toLocaleString('en-IN') }, grid:GRID, title:axisTitle('Strike (dotted line = spot)') },
          y:{ ticks:{ ...TICK, callback:(v)=> v+'%' }, grid:GRID, title:axisTitle('Implied volatility') },
        },
      },
    });

    const bs = cal.fits.blackScholes.rmseVolPts, best = cal.fits[cal.best];
    $('mcCalibFoot').textContent = cal.best === 'blackScholes'
      ? `Today's prices are close to a single volatility, so Black-Scholes already fits them well (average miss ${bs.toFixed(2)} vol points).`
      : `Black-Scholes has to use one volatility for every strike, so it misses today's prices by ${bs.toFixed(2)} volatility points on average. ` +
        `${FIT_STYLE[cal.best].name} reproduces the smile to within ${best.rmseVolPts.toFixed(2)} — about ${Math.max(bs/Math.max(best.rmseVolPts,1e-3),1).toFixed(0)}× closer. ` +
        `Press "Use calibrated settings" to price this contract with the market-fitted models.`;
  }

  async function calibrateToMarket(){
    const status = $('mcStatus');
    const symbol = $('pSymbol').value.trim();
    const expiry = $('expirySelect').value;
    if(!symbol || !/^\d{2}-[A-Za-z]{3}-\d{4}$/.test(expiry)){
      status.textContent = 'Pick a symbol and expiry first — calibration uses that expiry\'s live option chain.';
      status.className = 'mc-status err';
      return;
    }
    const qs = new URLSearchParams({ expiry, rate: $('pRate').value || 6.5, div: $('pDiv').value || 0 });
    $('mcCalibrate').disabled = true;
    status.className = 'mc-status';
    status.textContent = `Fitting models to the ${symbol} ${expiry} chain…`;
    try{
      renderCalibration(await apiGet(`/api/montecarlo/calibrate/${encodeURIComponent(symbol)}?${qs}`));
      status.textContent = 'Calibrated to today\'s market.';
    }catch(err){
      status.textContent = `Calibration failed: ${err.message}`;
      status.className = 'mc-status err';
    }finally{
      $('mcCalibrate').disabled = false;
    }
  }

  function applyCalibration(){
    if(!lastCalibration) return;
    Object.entries(lastCalibration.labSettings).forEach(([param, value])=>{
      const el = document.querySelector(`#mcSettings [data-param="${param}"]`);
      if(el) el.value = value;
    });
    $('mcSettings').open = true;
    run();
  }

  /* ---------- Scoreboard: which model is closest to the market price? ---------- */
  const SCORE_NAMES = { blackScholes:'Black-Scholes', heston:'Heston', jumps:'Merton jumps' };

  function isCalibrated(){
    return !!lastCalibration && lastCalibration.symbol === $('pSymbol').value.trim().toUpperCase()
      && lastCalibration.expiry === $('expirySelect').value
      && document.querySelector('#mcSettings [data-param="hXi"]').value !== '';
  }

  function renderScoreboard(data, market){
    const box = $('mcScore');
    if(!market){ box.hidden = true; return; }
    // Constant-vol simulation is Black-Scholes by another route, and American exercise answers a
    // different question (NSE options are European), so neither is ranked separately.
    const prices = { blackScholes:data.blackScholes.price };
    ['heston', 'jumps'].forEach(id=>{ if(data.models[id]) prices[id] = data.models[id].price; });
    const rows = Object.entries(prices)
      .map(([id, price])=>({ id, price, err:Math.abs(price - market), pct:Math.abs(price - market)/market }))
      .sort((a, b)=> a.err - b.err);
    const best = rows[0], bs = rows.find(r=>r.id==='blackScholes');
    const worst = Math.max(...rows.map(r=>r.err), 1e-9);
    const pct = (r)=> `${(r.pct*100).toFixed(1)}%`;

    let verdict;
    if(isCalibrated()){
      // Fitted to the whole chain, the best-fitting model gives this strike's "fair" price
      // relative to its neighbours; a gap means this quote is cheap or rich versus the chain.
      const fitId = lastCalibration.best;
      const fair = prices[fitId];
      const gap = (market - fair) / fair;
      const rel = Math.abs(gap) < 0.02 ? 'in line with' : gap < 0 ? 'cheap relative to' : 'rich relative to';
      verdict = `Calibrated to today's ${esc(lastCalibration.expiry)} chain, the best-fitting model (<strong>${SCORE_NAMES[fitId]}</strong>) ` +
        `values this option at <strong>${rupees(fair)}</strong>. The market price ${rupees(market)} is ` +
        `<strong>${Math.abs(gap*100).toFixed(1)}% ${gap < 0 ? 'below' : 'above'}</strong> that — ${rel} the rest of the chain` +
        (Math.abs(gap) < 0.02 ? '.' : ' (check the quote is not stale before acting on it).');
    }else if(best.id === 'blackScholes'){
      verdict = `With default settings Black-Scholes is closest to the market price (${rupees(market)}), off by <strong>${rupees(bs.err)}</strong> (${pct(bs)}). ` +
        `Calibrate to the market for a fairer comparison.`;
    }else{
      verdict = `<strong>${SCORE_NAMES[best.id]}</strong> is closest to the market price of ${rupees(market)}: off by <strong>${rupees(best.err)}</strong> ` +
        `(${pct(best)}) against <strong>${rupees(bs.err)}</strong> (${pct(bs)}) for Black-Scholes.`;
    }

    const lo = Math.min(...rows.map(r=>r.price)), hi = Math.max(...rows.map(r=>r.price));
    const inside = market >= lo && market <= hi;
    box.hidden = false;
    box.innerHTML = `<div class="mc-score-verdict">${verdict}</div>` +
      rows.map((r, i)=> `<div class="mc-score-row ${i===0 ? 'best' : ''}">
          <span class="nm">${esc(SCORE_NAMES[r.id])}${i===0 ? ' ★ closest' : ''}</span>
          <span class="val">${rupees(r.price)}</span>
          <span class="bar"><span style="width:${(r.err/worst*100).toFixed(1)}%"></span></span>
          <span class="err">${signed(r.price - market)}</span>
        </div>`).join('') +
      `<div class="mc-score-foot">Bars show each model's distance from the market price` +
      `${isCalibrated() ? ', using settings calibrated to today\'s chain' : ' using default settings — press "Calibrate to market", then "Use calibrated settings", for the fairest comparison'}. ` +
      `The models span ${rupees(lo)} – ${rupees(hi)}; the market is ${inside ? 'inside' : 'outside'} that range. ` +
      `Matching today's price is not a forecast — educational only.</div>`;
  }

  async function run(){
    const { inputs, market, error } = readInputs();
    const status = $('mcStatus');
    if(error){ status.textContent = error; status.className = 'mc-status err'; return; }
    const runId = ++lastRun;
    const params = { ...inputs, paths: $('mcPaths').value };
    if($('mcFixedSeed').checked) params.seed = 42;
    $('mcLab').classList.add('running');
    $('mcRun').disabled = true;
    status.className = 'mc-status';
    status.textContent = `Simulating ${Number(params.paths).toLocaleString('en-IN')} paths…`;
    try{
      const data = await apiGet('/api/montecarlo?' + new URLSearchParams(params));
      if(runId !== lastRun) return;   // a newer run started meanwhile
      render(data, market);
      renderScoreboard(data, market);
      renderConvergence(data);
      renderFan(data);
      status.textContent = `Done in ${data.elapsedMs.toFixed(0)} ms on the server.`;
      window.dispatchEvent(new CustomEvent('mc-lab:result', { detail:{ data, market } }));
    }catch(err){
      if(runId !== lastRun) return;
      status.textContent = `Simulation failed: ${err.message}`;
      status.className = 'mc-status err';
    }finally{
      if(runId === lastRun){ $('mcLab').classList.remove('running'); $('mcRun').disabled = false; }
    }
  }

  $('mcRun').addEventListener('click', run);
  $('mcCalibrate').addEventListener('click', calibrateToMarket);
  $('mcCalibApply').addEventListener('click', applyCalibration);
  $('mcFanModel').addEventListener('change', ()=>{ if(lastData) renderFan(lastData); });
  $('mcSettings').addEventListener('change', ()=>{ if(lastRun) run(); });
  $('mcPaths').addEventListener('change', ()=>{ if(lastRun) run(); });

  // Re-run automatically whenever the dashboard finishes a live fetch or local recalc.
  new MutationObserver(()=>{
    const text = $('statusText').textContent;
    if($('mcAuto').checked && /^(LIVE —|LOCAL RECALC)/.test(text)) run();
  }).observe($('statusText'), { childList:true, characterData:true, subtree:true });

  window.MCLab = { run, readInputs, rupees, signed, esc };
})();
