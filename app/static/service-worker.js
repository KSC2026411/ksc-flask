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

  console.log("🟢 SW: Install event fired");

  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );

  self.skipWaiting();

});


// =======================================
// ACTIVATE - CLEAN OLD CACHE
// =======================================
self.addEventListener("activate", event => {

  console.log("🟢 SW: Activate event fired");

  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) {
            console.log("🧹 Deleting old cache:", key);
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
        .catch(() => cached || caches.match("/offline"));

      return cached || networkFetch;

    })

  );

});


// =======================================
// PUSH NOTIFICATIONS + DEBUG
// =======================================
self.addEventListener("push", event => {

  console.log("🔥 SW: PUSH EVENT RECEIVED");

  event.waitUntil((async () => {

    let data = {};

    try {
      data = event.data ? event.data.json() : {};
      console.log("📩 PUSH DATA:", data);
    } catch (e) {
      console.log("❌ Push JSON error:", e);
      data = {};
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

    console.log("🔔 Showing notification:", title, options);

    await self.registration.showNotification(title, options);

    console.log("✅ Notification displayed");

    // APP BADGE (Android only)
    try {

      if (self.navigator && "setAppBadge" in self.navigator) {
        await self.navigator.setAppBadge(data.badge || 1);
        console.log("🔴 Badge set");
      }

    } catch (err) {
      console.log("⚠️ Badge not supported:", err);
    }

  })());

});


// =======================================
// NOTIFICATION CLICK
// =======================================
self.addEventListener("notificationclick", event => {

  console.log("👆 Notification clicked");

  event.notification.close();

  const url = event.notification.data?.url || "/";

  event.waitUntil(
    clients.openWindow(url)
  );

});