// Spindle push service worker. Plain JS, no imports.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

// iOS revokes push if a push arrives without a notification, so always show one
self.addEventListener("push", (event) => {
  let d = {};
  try {
    d = (event.data && event.data.json()) || {};
  } catch (e) {
    d = {};
  }
  event.waitUntil(self.registration.showNotification(d.title || "Spindle", {
    body: d.body || "",
    tag: d.tag,
    // replacing a same-tag banner still alerts; renotify without a tag throws
    renotify: !!d.tag,
    data: { url: d.url || "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  // same origin only; anything else opens the app root
  const raw = event.notification.data && event.notification.data.url;
  let url = "/";
  try {
    const u = new URL(typeof raw === "string" ? raw : "/", self.location.origin);
    if (u.origin === self.location.origin) url = u.href;
  } catch (e) {
    url = "/";
  }
  event.waitUntil((async () => {
    const [client] = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    if (!client) return self.clients.openWindow(url);
    await client.focus();
    // navigate() rejects for uncontrolled clients
    return client.navigate(url).catch(() => self.clients.openWindow(url));
  })());
});
