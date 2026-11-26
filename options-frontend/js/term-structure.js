/* Volatility term structure: at-the-money implied volatility for each of
   the next few expiries, from /api/term-structure. Reloads when a new
   symbol's chain loads and highlights the expiry currently selected. */
(function(){
  const $ = (id)=> document.getElementById(id);
  let data = null, loadedFor = null, chart = null;

  const foot = $('termFoot');

  async function load(symbol){
    loadedFor = symbol;
    $('termTag').textContent = 'loading…';
    try{
      const result = await apiGet(`/api/term-structure/${encodeURIComponent(symbol)}?max=6`);
      if(symbol !== loadedFor) return;          // another symbol was picked meanwhile
      data = result;
      draw();
    }catch(err){
      if(symbol !== loadedFor) return;
      $('termTag').textContent = 'unavailable';
      foot.textContent = `Could not load the term structure: ${err.message}`;
    }
  }

  function draw(){
    if(!data || !window.Chart) return;
    const pts = data.points;
    if(!pts.length){ $('termTag').textContent = 'no data'; foot.textContent = 'NSE reported no implied volatility for these expiries.'; return; }
    const selected = $('expirySelect').value;
    const tick = { color:'#5c5d54', font:{ family:'JetBrains Mono', size:9.5 } };
    if(chart) chart.destroy();
    chart = new Chart($('chartTerm').getContext('2d'), {
      type:'line',
      data:{ datasets:[{
        label:'ATM implied volatility', data:pts.map(p=>({ x:p.days, y:p.atmIv })),
        borderColor:'#ffb020', borderWidth:2, tension:0.25,
        pointRadius:pts.map(p=> p.expiry === selected ? 6 : 3),
        pointBackgroundColor:pts.map(p=> p.expiry === selected ? '#7fd4ff' : '#ffb020'),
      }]},
      options:{
        responsive:true, maintainAspectRatio:false, animation:false,
        plugins:{ legend:{ display:false }, tooltip:{ callbacks:{
          title:(it)=> it.length ? `${pts[it[0].dataIndex].expiry} · ${pts[it[0].dataIndex].days} days` : '',
          label:(c)=>{ const p = pts[c.dataIndex];
            return [`ATM IV ${p.atmIv.toFixed(2)}%`, `Expected move ±${p.expectedMovePct.toFixed(2)}% (±₹${Math.round(p.expectedMove).toLocaleString('en-IN')})`]; },
        } } },
        scales:{
          x:{ type:'linear', min:0, ticks:{ ...tick, maxRotation:0 }, grid:{ color:'#1d1e18' },
              title:{ display:true, text:'Days to expiry (blue dot = selected expiry)', color:'#7d7e72', font:{ family:'JetBrains Mono', size:9.5 } } },
          y:{ ticks:{ ...tick, callback:(v)=> v + '%' }, grid:{ color:'#1d1e18' } },
        },
      },
    });
    const first = pts[0], last = pts[pts.length - 1];
    $('termTag').textContent = data.shape === 'upward' ? 'upward' : data.shape === 'inverted' ? 'inverted' : 'flat';
    const reading = {
      upward: 'Later expiries carry more volatility: the market expects calmer conditions now than further out (the usual shape).',
      inverted: 'Near expiries carry more volatility than later ones: the market is pricing an event soon (results, policy, a big announcement).',
      flat: 'Volatility is about the same across expiries: no particular event is priced in.',
    }[data.shape];
    foot.textContent = `${reading} Nearest expiry (${first.expiry}): ATM IV ${first.atmIv.toFixed(1)}%, a typical move of ` +
      `±₹${Math.round(first.expectedMove).toLocaleString('en-IN')} by expiry` +
      (pts.length > 1 ? `; ${last.expiry}: ${last.atmIv.toFixed(1)}%.` : '.');
  }

  // Load once per symbol, when its chain has loaded; redraw when the expiry changes.
  new MutationObserver(()=>{
    if(/^LIVE CHAIN LOADED/.test($('statusText').textContent) && currentSymbol && currentSymbol !== loadedFor) load(currentSymbol);
  }).observe($('statusText'), { childList:true, characterData:true, subtree:true });
  $('expirySelect').addEventListener('change', draw);
})();
