/* Watchlist: save favourite symbols and switch to them with one click.
   Kept in this browser's localStorage (nothing is sent anywhere); works
   without it too, just without remembering between visits. */
(function(){
  const $ = (id)=> document.getElementById(id);
  const KEY = 'watchlist.v1', MAX = 12;
  const esc = (s)=> String(s).replace(/[&<>"]/g, (c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

  function load(){
    try{
      const list = JSON.parse(localStorage.getItem(KEY) || '[]');
      return Array.isArray(list) ? list.filter(s=> typeof s === 'string' && /^[A-Z0-9&_-]{1,20}$/.test(s)).slice(0, MAX) : [];
    }catch(e){ return []; }
  }
  let list = load();
  function save(){ try{ localStorage.setItem(KEY, JSON.stringify(list)); }catch(e){} }

  function render(){
    const current = currentSymbol;
    $('wlChips').innerHTML = list.length
      ? list.map(s=>`<span class="wl-chip ${s === current ? 'current' : ''}">
          <button class="wl-go" data-symbol="${esc(s)}" title="Load ${esc(s)}">${esc(s)}</button>
          <button class="wl-remove" data-symbol="${esc(s)}" title="Remove ${esc(s)} from the watchlist" aria-label="Remove ${esc(s)}">×</button>
        </span>`).join('')
      : '<span class="wl-empty">Pick a symbol, then ☆ to save it here.</span>';
    const btn = $('wlToggle');
    btn.hidden = !current;
    if(current){
      const saved = list.includes(current);
      btn.textContent = saved ? `★ ${current} saved` : `☆ Add ${current}`;
      btn.classList.toggle('saved', saved);
      btn.disabled = !saved && list.length >= MAX;
      btn.title = btn.disabled ? `The watchlist holds up to ${MAX} symbols` : saved ? 'Remove from the watchlist' : 'Save to the watchlist';
    }
  }

  $('wlToggle').addEventListener('click', ()=>{
    const s = currentSymbol;
    if(!s) return;
    list = list.includes(s) ? list.filter(x=> x !== s) : [...list, s].slice(0, MAX);
    save(); render();
  });
  $('wlChips').addEventListener('click', (e)=>{
    const go = e.target.closest('.wl-go'), rm = e.target.closest('.wl-remove');
    if(rm){ list = list.filter(x=> x !== rm.dataset.symbol); save(); render(); }
    else if(go && go.dataset.symbol !== currentSymbol){ selectSymbol(go.dataset.symbol); }
  });
  // Follow the selected symbol (the status line changes whenever one loads).
  new MutationObserver(render).observe($('statusText'), { childList:true, characterData:true, subtree:true });
  // Another tab changed the list.
  window.addEventListener('storage', (e)=>{ if(e.key === KEY){ list = load(); render(); } });
  render();
})();
