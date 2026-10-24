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
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil((async () => {
    const [client] = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    if (!client) return self.clients.openWindow(url);
    await client.focus();
    // navigate() rejects for uncontrolled clients
    return client.navigate(url).catch(() => self.clients.openWindow(url));
  })());
});
