// Klopot service worker (docs/WEB_PUSH.md): shows Web Push alerts and opens
// them on tap. Deliberately NO fetch handler and NO cache — the admin UI is
// always loaded fresh, so a deploy is never hidden behind a stale copy.
"use strict";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data && event.data.text() }; }
  const title = data.title || "Klopot";
  const options = {
    body: data.body || "",
    icon: "icons/icon-192.png",
    badge: "icons/badge-96.png",
    tag: data.tag || undefined,
    renotify: Boolean(data.tag),
    requireInteraction: data.severity === "critical",
    timestamp: data.ts || Date.now(),
    data: { url: data.url || "/admin/" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/admin/", self.location.origin);
  // Only ever open Klopot itself.
  if (target.origin !== self.location.origin) return;
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const open = wins.find((w) => new URL(w.url).pathname.startsWith("/admin/"));
    if (open) {
      await open.focus();
      if ("navigate" in open) return open.navigate(target.href);
      return undefined;
    }
    return self.clients.openWindow(target.href);
  })());
});
