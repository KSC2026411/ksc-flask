const CACHE_NAME = "ksc-logistics-v5";
const STATIC_ASSETS = [
    "/static/css/style.css",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png"
];
// =======================================
// INSTALL - CACHE CORE STATIC ASSETS
// =======================================
self.addEventListener("install", event => {
    console.log("🟢 SW: Install event fired");
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(STATIC_ASSETS);
        }).catch(error => {
            console.error("❌ SW: Failed to cache static assets:", error);
        })
    );
    self.skipWaiting();
});
// =======================================
// ACTIVATE - CLEAN OLD CACHE
// =======================================
self.addEventListener("activate", event => {
    console.log("🟢 SW: Activate event fired");
    event.waitUntil(
        caches.keys().then(keys => {
            return Promise.all(
                keys.map(key => {
                    if (key !== CACHE_NAME) {
                        console.log("🧹 SW: Deleting old cache:", key);
                        return caches.delete(key);
                    }
                    return null;
                })
            );
        }).then(() => {
            return self.clients.claim();
        })
    );
});
// =======================================
// FETCH - NEVER CACHE DYNAMIC FLASK PAGES
// =======================================
self.addEventListener("fetch", event => {
    const request = event.request;
    if (request.method !== "GET") {
        return;
    }
    const url = new URL(request.url);
    if (url.origin !== self.location.origin) {
        return;
    }
    // Always fetch Flask pages directly from the server.
    // This prevents stale CSRF tokens from being cached.
    if (request.mode === "navigate" || request.destination === "document") {
        event.respondWith(
            fetch(request).catch(() => {
                return caches.match("/offline");
            })
        );
        return;
    }
    // Only cache static assets.
    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.match(request).then(cached => {
                if (cached) {
                    return cached;
                }
                return fetch(request).then(networkResponse => {
                    if (!networkResponse || networkResponse.status !== 200) {
                        return networkResponse;
                    }
                    const clone = networkResponse.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(request, clone);
                    }).catch(error => {
                        console.log("⚠️ SW: Cache update failed:", error);
                    });
                    return networkResponse;
                });
            })
        );
    }
});
// =======================================
// PUSH NOTIFICATIONS
// =======================================
self.addEventListener("push", event => {
    console.log("🔥 SW: PUSH EVENT RECEIVED");
    event.waitUntil(
        (async () => {
            let data = {};
            try {
                data = event.data ? event.data.json() : {};
                console.log("📩 SW: PUSH DATA:", data);
            } catch (error) {
                console.error("❌ SW: Push JSON error:", error);
                data = {};
            }
            const title = data.title || "KSC Logistics";
            const message = data.message || data.body || "You have a new notification.";
            const notificationUrl = data.url || "/";
            const options = {
                body: message,
                icon: "/static/icons/icon-192.png",
                badge: "/static/icons/icon-192.png",
                data: {
                    url: notificationUrl
                },
                requireInteraction: false
            };
            console.log("🔔 SW: Showing notification:", title, options);
            await self.registration.showNotification(title, options);
            console.log("✅ SW: Notification displayed");
            try {
                if ("setAppBadge" in self) {
                    await self.setAppBadge(data.badge || 1);
                    console.log("🔴 SW: App badge set");
                }
            } catch (error) {
                console.log("⚠️ SW: App badge not supported:", error);
            }
        })()
    );
});
// =======================================
// NOTIFICATION CLICK
// =======================================
self.addEventListener("notificationclick", event => {
    console.log("👆 SW: Notification clicked");
    event.notification.close();
    const url = event.notification.data?.url || "/";
    event.waitUntil(
        clients.matchAll({
            type: "window",
            includeUncontrolled: true
        }).then(clientList => {
            for (const client of clientList) {
                if (client.url.includes(self.location.origin)) {
                    if ("navigate" in client) {
                        client.navigate(url);
                    }
                    if ("focus" in client) {
                        return client.focus();
                    }
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(url);
            }
        })
    );
});
// =======================================
// NOTIFICATION CLOSE
// =======================================
self.addEventListener("notificationclose", event => {
    console.log("🔕 SW: Notification closed");
});