/* Registers the service worker (sw.js) that makes the dashboard installable
   ("Add to Home Screen") and quick to load. Harmless where unsupported. */
if('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')){
  window.addEventListener('load', ()=>{
    navigator.serviceWorker.register('sw.js').catch((err)=> console.warn('Service worker not registered:', err));
  });
}
