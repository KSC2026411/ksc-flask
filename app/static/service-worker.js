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

  // Only cache GET requests
  if (request.method !== "GET") return;

  event.respondWith(

    caches.match(request).then(cached => {

      const fetchPromise = fetch(request)

        .then(networkResponse => {

          // Only cache valid responses
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

      return cached || fetchPromise;
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

  event.waitUntil(

    (async () => {

      // Show notification
      await self.registration.showNotification(title, options);

      // Set app icon badge count
      if ("setAppBadge" in self.registration) {
        try {
          await self.registration.setAppBadge(data.badge || 1);
        } catch (e) {
          console.log("Badge not supported");
        }
      }

    })()
  );
});



// =======================================
// NOTIFICATION CLICK
// =======================================

self.addEventListener("notificationclick", event => {

  event.notification.close();

  event.waitUntil(
    clients.openWindow(event.notification.data.url)
  );
});