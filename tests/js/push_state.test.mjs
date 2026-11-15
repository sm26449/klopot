// Web Push on this device (lib/push.js): what the card offers per browser.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom } from "./support/dom.mjs";

await setupDom();
if (!globalThis.crypto?.subtle) globalThis.crypto = (await import("node:crypto")).webcrypto;
const { pushState, browserEnv, keyBytes, endpointHash } = await import("../../app/admin_ui/static/lib/push.js");

const desktop = { secure: true, isIOS: false, standalone: false, hasServiceWorker: true, hasPushManager: true,
  hasNotification: true, permission: "default" };

test("a current desktop browser can enable push", () => {
  assert.equal(pushState(desktop), "ready");
  assert.equal(pushState({ ...desktop, permission: "granted" }), "ready");
});

test("blocked, insecure and old browsers say so", () => {
  assert.equal(pushState({ ...desktop, permission: "denied" }), "denied");
  assert.equal(pushState({ ...desktop, secure: false }), "insecure");
  assert.equal(pushState({ ...desktop, hasPushManager: false }), "unsupported");
});

test("iPhone in Safari is told to add Klopot to the Home Screen; the installed app can enable", () => {
  const safari = { ...desktop, isIOS: true, hasPushManager: false, hasNotification: false };
  assert.equal(pushState(safari), "ios-install");
  assert.equal(pushState({ ...desktop, isIOS: true, standalone: true }), "ready");
  assert.equal(pushState({ ...safari, hasServiceWorker: false }), "unsupported");   // iOS < 16.4
});

test("iPadOS posing as a Mac is detected by its touch points", () => {
  const w = { isSecureContext: true, navigator: { userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", maxTouchPoints: 5 },
    matchMedia: () => ({ matches: false }) };
  assert.equal(browserEnv(w).isIOS, true);
  assert.equal(browserEnv({ ...w, navigator: { ...w.navigator, maxTouchPoints: 0 } }).isIOS, false);
});

test("the VAPID key decodes to a 65-byte uncompressed point", () => {
  const key = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM";
  const bytes = keyBytes(key);
  assert.equal(bytes.length, 65);
  assert.equal(bytes[0], 4);
});

test("the endpoint hash matches the server's sha256 hex", async () => {
  assert.equal(await endpointHash("https://web.push.apple.com/abc"),
    "3333140aac13e319742cc23ced811fe20c92632f4fba808301416da9d9e50796");
});
