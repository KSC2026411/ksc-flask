const CACHE_NAME = "ksc-logistics-v3";

const STATIC_ASSETS = [
  "/",
  "/offline",
  "/static/css/style.css",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

// INSTALL (pre-cache core assets)
self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// ACTIVATE (remove old caches)
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

// FETCH (safe + offline-ready + production stable)
self.addEventListener("fetch", event => {
  const request = event.request;

  // ❗ Only cache GET requests (important fix)
  if (request.method !== "GET") return;

  event.respondWith(
    caches.match(request).then(cached => {

      const fetchPromise = fetch(request)
        .then(networkResponse => {

          // ❗ Only cache valid responses
          if (!networkResponse || networkResponse.status !== 200) {
            return networkResponse;
          }

          const clone = networkResponse.clone();

          caches.open(CACHE_NAME).then(cache => {
            cache.put(request, clone);
          });

          return networkResponse;
        })
        .catch(() => {
          // fallback chain
          return cached || caches.match("/offline");
        });

      return cached || fetchPromise;
    })
  );
});