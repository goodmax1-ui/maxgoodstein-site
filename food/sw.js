// Bump CACHE on every release so clients pick up the new shell.
const CACHE = 'food-v2';
const ASSETS = [
  '/food/',
  '/food/index.html',
  '/food/manifest.webmanifest',
  '/food/icon.svg',
  '/food/apple-touch-icon.png',
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

  // External APIs always go to the network — never cache.
  if (url.hostname.endsWith('anthropic.com') || url.hostname.endsWith('overpass-api.de')) return;

  // Stale-while-revalidate for everything else (HTML, fonts, icons).
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
