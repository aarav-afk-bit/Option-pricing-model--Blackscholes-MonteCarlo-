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
    return card('', m.label, m.price, lines, m.description);
  }

  function render(data, market){
    const bsPrice = data.blackScholes.price;
    const cards = [card('bs', 'Black-Scholes (formula)', bsPrice,
      [`<span class="meta">σ ${(data.inputs.vol*100).toFixed(2)}% · ${data.inputs.days} days</span>`],
      'Closed-form price: constant volatility, log-normal returns.')];
    Object.values(data.models).forEach(m=> cards.push(modelCard(m, bsPrice)));
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
  function renderFan(data){
    const fan = data.fan;
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
  $('mcPaths').addEventListener('change', ()=>{ if(lastRun) run(); });

  // Re-run automatically whenever the dashboard finishes a live fetch or local recalc.
  new MutationObserver(()=>{
    const text = $('statusText').textContent;
    if($('mcAuto').checked && /^(LIVE —|LOCAL RECALC)/.test(text)) run();
  }).observe($('statusText'), { childList:true, characterData:true, subtree:true });

  window.MCLab = { run, readInputs, rupees, signed, esc };
})();
