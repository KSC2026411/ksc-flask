const CACHE_NAME = "ksc-logistics-v3";

const STATIC_ASSETS = [
  "/",
  "/offline",
  "/static/css/style.css",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];


// =======================================
// INSTALL - CACHE CORE ASSETS
// =======================================
self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});


// =======================================
// ACTIVATE - CLEAN OLD CACHE
// =======================================
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


// =======================================
// FETCH - OFFLINE SUPPORT
// =======================================
self.addEventListener("fetch", event => {

  const request = event.request;

  if (request.method !== "GET") return;

  event.respondWith(
    caches.match(request).then(cached => {

      const networkFetch = fetch(request)
        .then(networkResponse => {

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
          return cached || caches.match("/offline");
        });

      return cached || networkFetch;
    })
  );
});


// =======================================
// PUSH NOTIFICATIONS
// =======================================
self.addEventListener("push", event => {

  let data = {};

  if (event.data) {
    data = event.data.json();
  }

  const title = data.title || "KSC Logistics";

  const options = {
    body: data.body || "New notification",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    data: {
      url: data.url || "/"
    }
  };

  event.waitUntil((async () => {

    // Show notification
    await self.registration.showNotification(title, options);

    // =======================================
    // APP BADGE (ONLY IF SUPPORTED)
    // =======================================
    try {

      if (self.navigator && "setAppBadge" in self.navigator) {
        await self.navigator.setAppBadge(data.badge || 1);
      }

    } catch (err) {
      console.log("Badge not supported:", err);
    }

  })());
});


// =======================================
// NOTIFICATION CLICK
// =======================================
self.addEventListener("notificationclick", event => {

  event.notification.close();

  const url = event.notification.data?.url || "/";

  event.waitUntil(
    clients.openWindow(url)
  );
});