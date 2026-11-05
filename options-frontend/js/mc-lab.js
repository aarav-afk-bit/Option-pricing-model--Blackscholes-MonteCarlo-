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
