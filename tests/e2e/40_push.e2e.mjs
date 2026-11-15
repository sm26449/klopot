// Web Push on this device (docs/WEB_PUSH.md): the installable app files, the
// Account card from "not set up" to an enabled device and back. The browser's
// PushManager is stubbed — a test cannot reach Apple / Google — but the
// service worker, the permission and every API call are real.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, randomBytes } from "node:crypto";
import { BASE, launch, session, go, until, axe, api } from "./support.mjs";

const b64url = (buf) => Buffer.from(buf).toString("base64url");
const VAPID_PRIVATE = generateKeyPairSync("ec", { namedCurve: "P-256" }).privateKey.export({ format: "jwk" }).d;
const DEVICE = {
  endpoint: `https://web.push.apple.com/e2e-${randomBytes(6).toString("hex")}`,
  keys: { p256dh: b64url(Buffer.concat([Buffer.from([4]), randomBytes(64)])), auth: b64url(randomBytes(16)) },
};

let browser, page, channelId;
before(async () => {
  browser = await launch();
  page = await session(browser);
  await page.context().addInitScript((dev) => {
    const sub = {
      endpoint: dev.endpoint, options: { applicationServerKey: null },
      toJSON: () => ({ endpoint: dev.endpoint, expirationTime: null, keys: dev.keys }),
      unsubscribe: async () => { localStorage.removeItem("e2e.push"); return true; },
    };
    // Headless Chromium never grants notifications; the permission prompt is the OS's anyway.
    Object.defineProperty(Notification, "permission", { get: () => "granted" });
    Notification.requestPermission = async () => "granted";
    PushManager.prototype.subscribe = async function subscribe(opts) {
      window.__e2eKeyLength = new Uint8Array(opts.applicationServerKey).length;
      localStorage.setItem("e2e.push", "1");
      return sub;
    };
    PushManager.prototype.getSubscription = async () => (localStorage.getItem("e2e.push") ? sub : null);
  }, DEVICE);
});
after(async () => {
  if (channelId) await api("DELETE", `/v1/channels/${channelId}`).catch(() => {});
  await browser?.close();
});

test("push: the app installs — manifest, icons and service worker are served", async () => {
  const res = await page.request.get(`${BASE}/admin/manifest.webmanifest`);
  assert.equal(res.status(), 200);
  const manifest = await res.json();
  assert.equal(manifest.display, "standalone");
  for (const icon of manifest.icons) assert.equal((await page.request.get(`${BASE}/admin/${icon.src}`)).status(), 200);
  assert.equal((await page.request.get(`${BASE}/admin/sw.js`)).status(), 200);
});

test("push: without a push channel the card says what is missing", async () => {
  await go(page, "account");
  const card = page.locator(".push-card");
  await card.waitFor();
  assert.match(await card.innerText(), /not set up yet/i);
  assert.equal(await card.getByRole("button", { name: /enable notifications/i }).count(), 0);
});

test("push: enable on this device, filter it, remove it", async () => {
  channelId = (await api("POST", "/v1/channels", {
    name: "e2e_phones", kind: "push", config: { vapid_private: VAPID_PRIVATE, vapid_subject: "mailto:e2e@example.com" },
  })).id;
  await go(page, "account");
  await page.reload();                      // same #/account: remount the card with the new channel
  const card = page.locator(".push-card");
  await card.getByRole("button", { name: /enable notifications/i }).click();
  await card.locator(".push-devices").waitFor();
  assert.equal(await page.evaluate(() => window.__e2eKeyLength), 65, "subscribed with the server's public key");
  assert.match(await card.innerText(), /this device/i);
  // The real service worker took the /admin/ scope.
  const scope = await page.evaluate(async () => (await navigator.serviceWorker.getRegistration("./"))?.scope);
  assert.ok(scope?.endsWith("/admin/"), scope);
  const [dev] = await api("GET", "/v1/push/subscriptions");
  assert.equal(dev.min_severity, "warning");
  assert.match(dev.label, /Chrome/);
  assert.deepEqual(await axe(page, ".push-card"), [], "push card axe");

  await card.getByRole("combobox", { name: /which alerts reach/i }).selectOption("critical");
  assert.ok(await until(async () => (await api("GET", "/v1/push/subscriptions"))[0]?.min_severity === "critical"));

  page.once("dialog", (d) => d.accept());
  await card.getByRole("button", { name: /turn off on this device/i }).click();
  await card.getByRole("button", { name: /enable notifications/i }).waitFor();
  assert.deepEqual(await api("GET", "/v1/push/subscriptions"), []);
});
