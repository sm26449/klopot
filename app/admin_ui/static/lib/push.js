// Web Push on this device (docs/WEB_PUSH.md): what the browser can do, and
// subscribe / unsubscribe with the service worker. `pushState` is pure (unit
// tested); the rest talks to the browser and the API.
import { api } from "./api.js";

/** What this browser can do about notifications, from a plain description of it. */
export function pushState(env) {
  if (!env.secure) return "insecure";
  // iPhone / iPad: Web Push exists only inside the app added to the Home Screen.
  if (env.isIOS && !env.standalone) return env.hasServiceWorker ? "ios-install" : "unsupported";
  if (!env.hasServiceWorker || !env.hasPushManager || !env.hasNotification) return "unsupported";
  if (env.permission === "denied") return "denied";
  return "ready";
}

/** The real browser's description (kept apart so pushState stays testable). */
export function browserEnv(w = globalThis) {
  const nav = w.navigator || {};
  const ua = nav.userAgent || "";
  // iPadOS reports itself as a Mac; touch points tell them apart.
  const isIOS = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && (nav.maxTouchPoints || 0) > 1);
  return {
    secure: Boolean(w.isSecureContext),
    isIOS,
    standalone: Boolean(w.matchMedia?.("(display-mode: standalone)").matches || nav.standalone),
    hasServiceWorker: "serviceWorker" in nav,
    hasPushManager: "PushManager" in w,
    hasNotification: "Notification" in w,
    permission: w.Notification?.permission || "default",
  };
}

/** VAPID public key (base64url) → the bytes pushManager.subscribe wants. */
export function keyBytes(b64url) {
  const b64 = (b64url + "=".repeat((4 - (b64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

/** sha256 hex of the endpoint — matches the server's endpoint_hash. */
export async function endpointHash(endpoint) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function registration() {
  return navigator.serviceWorker.register("./sw.js", { scope: "./" });
}

/** This browser's current subscription, or null (never prompts). */
export async function currentSubscription() {
  if (!("serviceWorker" in navigator)) return null;
  const reg = await navigator.serviceWorker.getRegistration("./");
  return reg ? reg.pushManager.getSubscription() : null;
}

function sameKey(sub, key) {
  const have = sub?.options?.applicationServerKey;
  if (!have) return true;   // older browsers do not expose it: trust it
  const a = new Uint8Array(have);
  return a.length === key.length && a.every((v, i) => v === key[i]);
}

/**
 * Ask for permission (must run inside a tap), subscribe with the server's key
 * and register the device. Returns the registered device (API row).
 */
export async function enablePush(publicKey) {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    const err = new Error(permission);
    err.code = permission === "denied" ? "denied" : "dismissed";
    throw err;
  }
  const reg = await registration();
  await navigator.serviceWorker.ready;
  const key = keyBytes(publicKey);
  let sub = await reg.pushManager.getSubscription();
  // The server's key changed (rotated): the old subscription is useless.
  if (sub && !sameKey(sub, key)) { await sub.unsubscribe(); sub = null; }
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  const json = sub.toJSON();
  return api.post("/v1/push/subscriptions", { endpoint: json.endpoint, keys: json.keys });
}

/** Stop push on this browser; the server row is removed by the caller (admin). */
export async function unsubscribeHere() {
  const sub = await currentSubscription();
  if (sub) await sub.unsubscribe();
}
