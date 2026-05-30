// Bump CACHE on every release so clients pick up the new shell.
const CACHE = 'parks-v1';
const ASSETS = [
  '/parks/',
  '/parks/index.html',
  '/parks/reps.json',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  // Don't cache the live data sources — these change and we already cache in
  // localStorage at the app layer with smart TTLs.
  if (url.hostname === 'data.cityofnewyork.us') return;
  if (url.hostname.endsWith('en.wikipedia.org')) return;
  if (url.hostname === 'parks-proxy.goodmax1.workers.dev') return;
  if (url.hostname === 'tree-map.nycgovparks.org') return;

  const isShell = e.request.mode === 'navigate' ||
    url.pathname === '/parks/' ||
    url.pathname === '/parks/index.html' ||
    url.pathname === '/parks/reps.json';

  if (isShell) {
    // Network-first for the app shell + data files so a fresh deploy shows up
    // immediately. Fall back to cache only when offline.
    e.respondWith(
      fetch(e.request).then(resp => {
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return resp;
      }).catch(() => caches.match(e.request))
    );
    return;
  }

  // SWR for static assets (fonts, Wikipedia images, congress.gov headshots, favicons).
  e.respondWith(
    caches.match(e.request).then(cached => {
      const fetchPromise = fetch(e.request).then(resp => {
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return resp;
      }).catch(() => cached);
      return cached || fetchPromise;
    })
  );
});
