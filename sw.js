const CACHE_NAME = 'current-shell-v5';
const SHELL = [
  '/current/',
  '/current-client.js',
  '/mood-card.js',
  '/place-photos.js',
  '/current-moments.js',
  '/current-moments.css',
  '/reach-policy.js',
  '/voice-worklet.mjs',
  '/manifest.webmanifest',
  '/pwa/icon-192.png',
  '/pwa/icon-512.png',
  '/assets/moments/sunset.jpg',
  '/assets/moments/leaf.jpg',
  '/assets/moments/cloud.jpg',
  '/assets/moments/dew.jpg',
  '/assets/moments/book.jpg',
  '/assets/moments/cafe.jpg',
  '/assets/moments/food.jpg',
  '/assets/moments/bar.jpg',
  '/assets/moments/city.jpg',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

  // Network first keeps hackathon builds fresh; the cached shell is only the
  // fallback when the phone briefly loses connectivity.
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then(cached => cached || caches.match('/current/'))),
  );
});
