/* Print / save as PDF. css/print.css lays the page out for paper (including
   scaling the charts to fit); this adds a report header naming the contract
   and time, and redraws the charts once printing ends. */
(function(){
  const $ = (id)=> document.getElementById(id);

  const header = document.createElement('div');
  header.className = 'print-header';
  document.body.insertBefore(header, document.body.firstChild);

  function fillHeader(){
    const symbol = $('pSymbol').value || 'No contract selected';
    const type = $('btnPut').classList.contains('active') ? 'PUT' : 'CALL';
    const strike = $('pStrike').value, expiry = $('expirySelect').value;
    const contract = strike ? `${symbol} ${Number(strike).toLocaleString('en-IN')} ${type}${/\d{4}$/.test(expiry) ? ' · expires ' + expiry : ''}` : symbol;
    const spot = $('pSpot').value ? ` · spot ₹${Number($('pSpot').value).toLocaleString('en-IN')}` : '';
    header.innerHTML = '';
    const title = document.createElement('div');
    title.className = 'print-title';
    title.textContent = `Options analysis — ${contract}`;
    const meta = document.createElement('div');
    meta.className = 'print-meta';
    meta.textContent = `${new Date().toLocaleString('en-IN', { dateStyle:'medium', timeStyle:'short' })}${spot} · ` +
      `${$('statusText').textContent} · Model output for education, not investment advice.`;
    header.append(title, meta);
  }

  function resizeCharts(){
    if(window.Chart && Chart.instances) Object.values(Chart.instances).forEach(c=>{ try{ c.resize(); }catch(e){} });
  }

  window.addEventListener('beforeprint', fillHeader);
  window.addEventListener('afterprint', resizeCharts);
  $('printReportBtn').addEventListener('click', ()=>{ fillHeader(); window.print(); });
})();
