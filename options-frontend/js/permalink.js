/* Shareable links: the URL hash records the selected contract, e.g.
     #s=NIFTY&e=27-Jan-2027&k=24800&t=put
   so a refresh, a bookmark or a link sent to someone reopens the same option
   and runs the analysis. Self-contained: it reads app.js's state and drives
   the same controls a user would, so app.js needs no hooks. */
(function(){
  const $ = (id)=> document.getElementById(id);
  const EXPIRY_RE = /^\d{2}-[A-Za-z]{3}-\d{4}$/;
  let restoring = false;

  function statusText(){ return $('statusText').textContent; }

  function waitFor(test, timeoutMs){
    return new Promise((resolve)=>{
      const started = Date.now();
      (function poll(){
        if(test()) return resolve(true);
        if(Date.now() - started > timeoutMs) return resolve(false);
        setTimeout(poll, 100);
      })();
    });
  }

  /* Current selection -> URL hash (replaceState, so the back button isn't flooded). */
  function writeHash(){
    if(restoring || !currentSymbol) return;
    const p = new URLSearchParams({ s: currentSymbol });
    const expiry = $('expirySelect').value;
    if(EXPIRY_RE.test(expiry)) p.set('e', expiry);
    const strike = $('strikeSelect').value;
    if(strike && !isNaN(Number(strike))) p.set('k', strike);
    p.set('t', $('btnPut').classList.contains('active') ? 'put' : 'call');
    const hash = '#' + p.toString();
    if(location.hash !== hash) history.replaceState(null, '', hash);
  }
  const writeSoon = ()=> setTimeout(writeHash, 0);   // after app.js's own handlers have run

  function selectOption(select, value){
    if(![...select.options].some(o=>o.value === value)) return false;
    if(select.value !== value){
      select.value = value;
      select.dispatchEvent(new Event('change'));
    }
    return true;
  }

  /* URL hash -> selection, then Fetch Live. Each step waits for the app to finish the previous one. */
  async function restore(){
    const p = new URLSearchParams(location.hash.slice(1));
    const symbol = (p.get('s') || '').trim().toUpperCase();
    if(!/^[A-Z0-9&_-]{1,20}$/.test(symbol)) return;
    restoring = true;
    try{
      // Let the startup health check finish (a sleeping server can take a minute to wake).
      if(!await waitFor(()=> /CONNECTED|UNREACHABLE|LOADED|LIVE|LOCAL/.test(statusText()), 120000)) return;
      if(/UNREACHABLE/.test(statusText())) return;

      if(currentSymbol !== symbol || !currentChain) selectSymbol(symbol);
      const chainReady = ()=> currentSymbol === symbol && currentChain && !$('strikeSelect').disabled;
      if(!await waitFor(()=> chainReady() || /FAILED/.test(statusText()), 90000) || !chainReady()) return;

      const expiry = p.get('e');
      if(expiry && EXPIRY_RE.test(expiry) && selectOption($('expirySelect'), expiry)){
        // Switching expiry may fetch that expiry's strikes.
        if(!await waitFor(()=> !$('strikeSelect').disabled && !/FETCHING/.test(statusText()), 90000)) return;
      }
      const strike = p.get('k');
      if(strike) selectOption($('strikeSelect'), String(Number(strike)));
      $(p.get('t') === 'put' ? 'btnPut' : 'btnCall').click();
    }finally{
      restoring = false;
    }
    writeHash();
    $('fetchBtn').click();
  }

  async function copyLink(){
    writeHash();
    const btn = $('copyLinkBtn');
    if(!currentSymbol){ btn.textContent = 'pick a contract first'; }
    else{
      try{
        await navigator.clipboard.writeText(location.href);
        btn.textContent = 'link copied ✓';
      }catch(e){
        window.prompt('Copy this link:', location.href);   // clipboard blocked (e.g. not https)
        btn.textContent = 'copy link';
        return;
      }
    }
    setTimeout(()=>{ btn.textContent = 'copy link'; }, 1800);
  }

  ['expirySelect', 'strikeSelect'].forEach(id=> $(id).addEventListener('change', writeSoon));
  ['btnCall', 'btnPut'].forEach(id=> $(id).addEventListener('click', writeSoon));
  $('chainTable').addEventListener('click', writeSoon);   // picking a strike in the option chain
  new MutationObserver(()=>{ if(/^(LIVE|LOCAL RECALC)/.test(statusText())) writeSoon(); })
    .observe($('statusText'), { childList:true, characterData:true, subtree:true });
  $('copyLinkBtn').addEventListener('click', copyLink);
  window.addEventListener('hashchange', ()=>{ if(!restoring) restore(); });

  restore();
})();
