/* Service worker: makes the dashboard installable and quick to open on a
   slow connection by caching the app's own files. Live market data always
   comes from the backend and is never cached here (it's on another origin).

   - Page loads: network first, so a new deploy shows up immediately; the
     cached copy is only used when offline.
   - Other files (CSS, JS, icons, Chart.js, fonts): served from the cache
     at once and refreshed in the background (stale-while-revalidate).
   Bump CACHE when this file's strategy changes; old caches are deleted. */
const CACHE = 'options-terminal-v1';
const CORE = [
  './', 'index.html', 'manifest.webmanifest',
  'css/style.css', 'css/mc-lab.css',
  'js/config.js', 'js/pricing.js', 'js/api.js', 'js/mc-lab.js', 'js/app.js', 'js/glossary.js', 'js/pwa.js',
  'data/nse_companies.json', 'icons/icon-192.png', 'icons/favicon.png',
];
// Third-party files the page needs to render (cached when first fetched).
const CACHEABLE_HOSTS = ['cdnjs.cloudflare.com', 'fonts.googleapis.com', 'fonts.gstatic.com'];

self.addEventListener('install', (event)=>{
  // Cache what we can; one missing file must not block installation.
  event.waitUntil(caches.open(CACHE).then((cache)=>
    Promise.allSettled(CORE.map((url)=> cache.add(new Request(url, { cache:'reload' }))))
  ).then(()=> self.skipWaiting()));
});

self.addEventListener('activate', (event)=>{
  event.waitUntil(caches.keys()
    .then((keys)=> Promise.all(keys.filter((k)=> k !== CACHE).map((k)=> caches.delete(k))))
    .then(()=> self.clients.claim()));
});

async function networkFirst(request){
  const cache = await caches.open(CACHE);
  try{
    const response = await fetch(request);
    if(response.ok) cache.put(request, response.clone());
    return response;
  }catch(err){
    return (await cache.match(request)) || (await cache.match('index.html')) || Response.error();
  }
}

async function staleWhileRevalidate(request, event){
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  const refresh = fetch(request).then((response)=>{
    if(response.ok || response.type === 'opaque') cache.put(request, response.clone());
    return response;
  }).catch(()=> cached);
  if(cached){ event.waitUntil(refresh); return cached; }
  return refresh;
}

self.addEventListener('fetch', (event)=>{
  const request = event.request;
  if(request.method !== 'GET') return;
  const url = new URL(request.url);
  const sameOrigin = url.origin === self.location.origin;
  if(!sameOrigin && !CACHEABLE_HOSTS.includes(url.hostname)) return;   // the API and anything else: untouched
  if(request.mode === 'navigate') event.respondWith(networkFirst(request));
  else event.respondWith(staleWhileRevalidate(request, event));
});
