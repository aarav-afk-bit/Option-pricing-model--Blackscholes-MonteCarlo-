/* Strategy builder: combine several options on one underlying and expiry
   (straddles, strangles, spreads, iron condors, or any custom mix) and see
   the combined payoff, breakevens, maximum profit/loss, probability of
   profit and net Greeks. Uses pricing.js; the maths below has no DOM
   dependencies and is unit-tested in node. */

/* ---------- Pure maths ---------- */
const StrategyMath = (function(){
  // A leg: { side:'buy'|'sell', type:'call'|'put', strike, qty (lots), premium (per unit), iv (decimal) }
  const sign = (leg)=> leg.side === 'sell' ? -1 : 1;
  const intrinsic = (leg, S)=> leg.type === 'call' ? Math.max(S - leg.strike, 0) : Math.max(leg.strike - S, 0);

  /* Net premium per unit of the whole position: positive = you pay (debit), negative = you receive (credit). */
  function netPremium(legs){
    return legs.reduce((sum, l)=> sum + sign(l) * l.qty * l.premium, 0);
  }

  /* Profit/loss at expiry per unit of underlying (multiply by lot size for rupees per lot). */
  function pnlAtExpiry(legs, S){
    return legs.reduce((sum, l)=> sum + sign(l) * l.qty * (intrinsic(l, S) - l.premium), 0);
  }

  /* Profit/loss today if the underlying were at S, valuing each leg with Black-Scholes at its own IV. */
  function pnlToday(legs, S, T, r, q){
    return legs.reduce((sum, l)=>{
      const bs = blackScholes(S, l.strike, T, r, l.iv, q);
      return sum + sign(l) * l.qty * ((l.type === 'call' ? bs.call : bs.put) - l.premium);
    }, 0);
  }

  /* Slope of the expiry P&L above the highest strike: net number of calls held. */
  const upperSlope = (legs)=> legs.reduce((s, l)=> s + (l.type === 'call' ? sign(l) * l.qty : 0), 0);

  /* Expiry P&L is piecewise linear with kinks at the strikes, so its extremes and
     zero crossings can be found exactly from the values at 0 and at each strike. */
  function analyse(legs){
    const strikes = [...new Set(legs.map(l=>l.strike))].sort((a, b)=> a - b);
    const points = [0, ...strikes].map(S=>({ S, pnl: pnlAtExpiry(legs, S) }));
    const slopeUp = upperSlope(legs);
    const values = points.map(p=>p.pnl);
    const maxProfit = slopeUp > 1e-12 ? Infinity : Math.max(...values);
    const maxLoss = slopeUp < -1e-12 ? -Infinity : Math.min(...values);

    const breakevens = [];
    for(let i = 1; i < points.length; i++){
      const a = points[i-1], b = points[i];
      if(a.pnl === 0 && i === 1 && a.S > 0) breakevens.push(a.S);
      if((a.pnl < 0 && b.pnl > 0) || (a.pnl > 0 && b.pnl < 0)){
        breakevens.push(a.S + (b.S - a.S) * (0 - a.pnl) / (b.pnl - a.pnl));
      }else if(b.pnl === 0 && (i < points.length - 1 || Math.abs(slopeUp) > 1e-12)){
        breakevens.push(b.S);
      }
    }
    const last = points[points.length - 1];
    if(Math.abs(slopeUp) > 1e-12 && Math.sign(last.pnl) === -Math.sign(slopeUp) && last.pnl !== 0){
      breakevens.push(last.S - last.pnl / slopeUp);   // crosses zero beyond the highest strike
    }
    return { maxProfit, maxLoss, breakevens: [...new Set(breakevens.map(b=>Math.round(b * 100) / 100))], strikes };
  }

  /* Risk-neutral probability of finishing with a profit: P&L > 0 on the intervals
     between breakevens, each weighted by the lognormal probability of S_T landing there. */
  function probabilityOfProfit(legs, S, T, r, q, sigma){
    const { breakevens } = analyse(legs);
    const edges = [0, ...breakevens, Infinity];
    let p = 0;
    for(let i = 1; i < edges.length; i++){
      const lo = edges[i-1], hi = edges[i];
      const mid = hi === Infinity ? lo * 1.5 + 1 : (lo + hi) / 2;
      if(pnlAtExpiry(legs, mid) > 0){
        const above = (x)=> x <= 0 ? 1 : x === Infinity ? 0 : probAbove(S, x, T, r, sigma, q);
        p += above(lo) - above(hi);
      }
    }
    return Math.min(Math.max(p, 0), 1);
  }

  /* Net Greeks per unit (delta, gamma, theta per day, vega per 1% IV). */
  function netGreeks(legs, S, T, r, q){
    return legs.reduce((g, l)=>{
      const k = bsGreeks(S, l.strike, T, r, l.iv, q);
      const w = sign(l) * l.qty;
      g.delta += w * (l.type === 'call' ? k.callDelta : k.putDelta);
      g.gamma += w * k.gamma;
      g.thetaPerDay += w * (l.type === 'call' ? k.callTheta : k.putTheta) / 365;
      g.vegaPer1 += w * k.vega / 100;
      return g;
    }, { delta:0, gamma:0, thetaPerDay:0, vegaPer1:0 });
  }

  /* Ready-made strategies around the at-the-money strike; `step` is the chain's strike spacing. */
  const PRESETS = {
    longStraddle:  { name:'Long straddle',    view:'Big move either way',     legs:(k, s)=>[['buy','call',k], ['buy','put',k]] },
    shortStraddle: { name:'Short straddle',   view:'Price stays put',         legs:(k, s)=>[['sell','call',k], ['sell','put',k]] },
    longStrangle:  { name:'Long strangle',    view:'Very big move either way', legs:(k, s)=>[['buy','call',k + 2*s], ['buy','put',k - 2*s]] },
    bullCall:      { name:'Bull call spread', view:'Moderately bullish',      legs:(k, s)=>[['buy','call',k], ['sell','call',k + 2*s]] },
    bearPut:       { name:'Bear put spread',  view:'Moderately bearish',      legs:(k, s)=>[['buy','put',k], ['sell','put',k - 2*s]] },
    ironCondor:    { name:'Iron condor',      view:'Stays in a range',        legs:(k, s)=>[['sell','put',k - 2*s], ['buy','put',k - 4*s], ['sell','call',k + 2*s], ['buy','call',k + 4*s]] },
  };

  return { netPremium, pnlAtExpiry, pnlToday, analyse, probabilityOfProfit, netGreeks, PRESETS };
})();

/* ---------- Page wiring ---------- */
if(typeof document !== 'undefined') (function(){
  const $ = (id)=> document.getElementById(id);
  const rupees = (v, dec=0)=> !isFinite(v) ? (v > 0 ? 'Unlimited' : 'Unlimited loss') :
    (v < 0 ? '−' : '') + '₹' + Math.abs(v).toLocaleString('en-IN', { minimumFractionDigits:dec, maximumFractionDigits:dec });
  const esc = (s)=> String(s).replace(/[&<>"]/g, (c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  let legs = [];
  let chart = null;

  function context(){
    const legsForExpiry = currentChain && currentChain.chain && currentChain.chain[$('expirySelect').value];
    if(!legsForExpiry) return null;
    const strikes = Object.keys(legsForExpiry).map(Number).sort((a, b)=> a - b);
    const S = parseFloat($('pSpot').value) || currentChain.spot;
    const steps = strikes.slice(1).map((k, i)=> k - strikes[i]).filter(d=> d > 0);
    const ref = companiesRef.find(c=> c.symbol === currentSymbol);
    return {
      chain: legsForExpiry, strikes, S,
      step: steps.length ? Math.min(...steps) : S * 0.01,
      days: parseFloat($('pDays').value) || 1,
      r: (parseFloat($('pRate').value) || 6.5) / 100,
      q: (parseFloat($('pDiv').value) || 0) / 100,
      vol: (parseFloat($('pVol').value) || 15) / 100,
      lot: ref && ref.lotSize ? ref.lotSize : 1,
    };
  }

  const nearest = (strikes, k)=> strikes.reduce((best, s)=> Math.abs(s - k) < Math.abs(best - k) ? s : best, strikes[0]);

  /* Market price and IV for one leg from the chain: bid/ask mid if quoted, else last price, else the model. */
  function quote(ctx, type, strike){
    const leg = (ctx.chain[strike] || {})[type === 'call' ? 'CE' : 'PE'] || {};
    const iv = leg.impliedVolatility > 0 ? leg.impliedVolatility / 100 : ctx.vol;
    let premium = leg.bid > 0 && leg.ask >= leg.bid ? (leg.bid + leg.ask) / 2 : leg.lastPrice;
    if(!(premium > 0)){
      const bs = blackScholes(ctx.S, strike, ctx.days / 365, ctx.r, iv, ctx.q);
      premium = type === 'call' ? bs.call : bs.put;
    }
    return { premium: Math.round(premium * 100) / 100, iv };
  }

  function applyPreset(id){
    const ctx = context();
    if(!ctx){ showMessage('Load a symbol and expiry first — the builder prices legs from the live option chain.'); return; }
    const atm = nearest(ctx.strikes, ctx.S);
    legs = StrategyMath.PRESETS[id].legs(atm, ctx.step).map(([side, type, k])=>{
      const strike = nearest(ctx.strikes, k);
      return { side, type, strike, qty:1, ...quote(ctx, type, strike) };
    });
    render();
  }

  function addLeg(){
    const ctx = context();
    if(!ctx){ showMessage('Load a symbol and expiry first.'); return; }
    const strike = nearest(ctx.strikes, ctx.S);
    legs.push({ side:'buy', type:'call', strike, qty:1, ...quote(ctx, 'call', strike) });
    render();
  }

  function showMessage(text){ $('stratResults').innerHTML = `<div class="strat-empty">${esc(text)}</div>`; }

  function renderLegs(ctx){
    const opts = (sel, list)=> list.map(([v, t])=>`<option value="${v}" ${v == sel ? 'selected' : ''}>${t}</option>`).join('');
    $('stratLegs').innerHTML = legs.map((l, i)=>`
      <tr data-i="${i}">
        <td><select data-f="side">${opts(l.side, [['buy','Buy'], ['sell','Sell']])}</select></td>
        <td><select data-f="type">${opts(l.type, [['call','Call'], ['put','Put']])}</select></td>
        <td><select data-f="strike">${opts(l.strike, ctx.strikes.map(k=>[k, k.toLocaleString('en-IN')]))}</select></td>
        <td><input data-f="qty" type="number" min="1" step="1" value="${l.qty}"></td>
        <td><input data-f="premium" type="number" min="0" step="0.05" value="${l.premium}"></td>
        <td class="iv">${(l.iv * 100).toFixed(1)}%</td>
        <td><button class="strat-remove" title="Remove leg">✕</button></td>
      </tr>`).join('') || '<tr><td colspan="7" class="strat-empty">Pick a ready-made strategy or add legs.</td></tr>';
  }

  function render(){
    const ctx = context();
    if(!ctx){ showMessage('Load a symbol and expiry first — the builder prices legs from the live option chain.'); return; }
    renderLegs(ctx);
    if(!legs.length){ $('stratResults').innerHTML = ''; if(chart){ chart.destroy(); chart = null; } return; }

    const T = ctx.days / 365, L = ctx.lot;
    const a = StrategyMath.analyse(legs);
    const net = StrategyMath.netPremium(legs) * L;
    const g = StrategyMath.netGreeks(legs, ctx.S, T, ctx.r, ctx.q);
    const atmIv = quote(ctx, 'call', nearest(ctx.strikes, ctx.S)).iv;
    const pop = StrategyMath.probabilityOfProfit(legs, ctx.S, T, ctx.r, ctx.q, atmIv);
    const stat = (k, v, cls='')=> `<div class="strat-stat"><span class="k">${k}</span><span class="v ${cls}">${v}</span></div>`;
    $('stratResults').innerHTML = `
      <div class="strat-stats">
        ${stat(net >= 0 ? 'Net debit (you pay)' : 'Net credit (you receive)', rupees(Math.abs(net)))}
        ${stat('Max profit', rupees(a.maxProfit * L), 'pos')}
        ${stat('Max loss', rupees(a.maxLoss * L), 'neg')}
        ${stat('Breakeven' + (a.breakevens.length === 1 ? '' : 's'), a.breakevens.length ? a.breakevens.map(b=>b.toLocaleString('en-IN', {maximumFractionDigits:0})).join(' · ') : 'none')}
        ${stat('Chance of profit', (pop * 100).toFixed(0) + '%')}
        ${stat('Net delta', (g.delta * L).toFixed(1))}
        ${stat('Theta / day', rupees(g.thetaPerDay * L), g.thetaPerDay >= 0 ? 'pos' : 'neg')}
        ${stat('Vega / 1% IV', rupees(g.vegaPer1 * L))}
      </div>
      <div class="strat-note">Per ${L > 1 ? `lot of ${L}` : 'unit'}${legs.some(l=>l.qty > 1) ? ', with the quantities above' : ''}. ` +
      `Chance of profit is risk-neutral at the ATM IV of ${(atmIv*100).toFixed(1)}% — a model estimate, not a forecast.</div>`;
    drawChart(ctx, a);
  }

  function drawChart(ctx, a){
    if(!window.Chart) return;
    const T = ctx.days / 365, L = ctx.lot;
    // Zoom to the strikes (plus a margin) and round the ends to whole strike steps.
    const kMin = Math.min(ctx.S, ...a.strikes), kMax = Math.max(ctx.S, ...a.strikes);
    const pad = Math.max(kMax - kMin, ctx.S * 0.04);
    const snap = ctx.step * Math.max(1, Math.round(pad / ctx.step / 4));
    const lo = Math.floor((kMin - pad) / snap) * snap, hi = Math.ceil((kMax + pad) / snap) * snap;
    const xs = Array.from({ length:121 }, (_, i)=> lo + (hi - lo) * i / 120);
    const expiry = xs.map(x=>({ x, y: StrategyMath.pnlAtExpiry(legs, x) * L }));
    const today = xs.map(x=>({ x, y: StrategyMath.pnlToday(legs, x, T, ctx.r, ctx.q) * L }));
    if(chart) chart.destroy();
    const tick = { color:'#5c5d54', font:{ family:'JetBrains Mono', size:9.5 } };
    chart = new Chart($('stratChart').getContext('2d'), {
      type:'line',
      data:{ datasets:[
        { label:'At expiry', data:expiry, borderColor:'#ffb020', borderWidth:2.5, pointRadius:0,
          fill:{ target:'origin', above:'rgba(61,220,132,0.12)', below:'rgba(255,92,92,0.12)' } },
        { label:'Today', data:today, borderColor:'#7fd4ff', borderWidth:1.5, borderDash:[5,4], pointRadius:0 },
        { label:'Spot', data:[{ x:ctx.S, y:Math.min(...expiry.map(p=>p.y)) }, { x:ctx.S, y:Math.max(...expiry.map(p=>p.y)) }],
          borderColor:'rgba(155,156,143,0.6)', borderWidth:1, borderDash:[2,3], pointRadius:0 },
      ]},
      options:{
        responsive:true, maintainAspectRatio:false, animation:false,
        interaction:{ mode:'index', intersect:false },
        plugins:{ legend:{ labels:{ color:'#9b9c8f', font:{ family:'JetBrains Mono', size:10 }, boxWidth:12 } },
          tooltip:{ callbacks:{ title:(it)=> it.length ? `Underlying ${Math.round(it[0].parsed.x).toLocaleString('en-IN')}` : '',
                                label:(c)=> `${c.dataset.label}: ${rupees(c.parsed.y)}` } } },
        scales:{
          x:{ type:'linear', min:lo, max:hi, ticks:{ ...tick, maxRotation:0, callback:(v)=> Math.round(v).toLocaleString('en-IN') }, grid:{ color:'#1d1e18' },
              title:{ display:true, text:'Underlying price at expiry', color:'#7d7e72', font:{ family:'JetBrains Mono', size:9.5 } } },
          y:{ ticks:{ ...tick, callback:(v)=> rupees(v) }, grid:{ color:'#1d1e18' },
              title:{ display:true, text:`Profit / loss per ${L > 1 ? 'lot' : 'unit'}`, color:'#7d7e72', font:{ family:'JetBrains Mono', size:9.5 } } },
        },
      },
    });
  }

  $('stratPresets').addEventListener('click', (e)=>{
    const b = e.target.closest('[data-preset]');
    if(!b) return;
    document.querySelectorAll('#stratPresets [data-preset]').forEach(x=> x.classList.toggle('active', x === b));
    applyPreset(b.dataset.preset);
  });
  $('stratAdd').addEventListener('click', addLeg);
  $('stratLegs').addEventListener('change', (e)=>{
    const tr = e.target.closest('tr[data-i]');
    if(!tr) return;
    const leg = legs[Number(tr.dataset.i)], f = e.target.dataset.f;
    if(f === 'qty') leg.qty = Math.max(1, Math.round(Number(e.target.value) || 1));
    else if(f === 'premium') leg.premium = Math.max(0, Number(e.target.value) || 0);
    else if(f === 'strike') leg.strike = Number(e.target.value);
    else leg[f] = e.target.value;
    if(f === 'type' || f === 'strike'){ const ctx = context(); if(ctx) Object.assign(leg, quote(ctx, leg.type, leg.strike)); }
    render();
  });
  $('stratLegs').addEventListener('click', (e)=>{
    const btn = e.target.closest('.strat-remove');
    if(!btn) return;
    legs.splice(Number(btn.closest('tr').dataset.i), 1);
    render();
  });
  // A new symbol or expiry invalidates the legs' strikes and prices.
  $('expirySelect').addEventListener('change', ()=>{ legs = []; render(); });
  new MutationObserver(()=>{
    if(/^LIVE CHAIN LOADED/.test($('statusText').textContent) && legs.length && !legs.every(l=> context() && context().chain[l.strike])){
      legs = []; render();
    }
  }).observe($('statusText'), { childList:true, characterData:true, subtree:true });

  window.StrategyBuilder = { render, legs: ()=> legs };
})();
