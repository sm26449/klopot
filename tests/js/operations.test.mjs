import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const { OperationsView } = await import("../../app/admin_ui/static/views/operations.js");
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");

const SNAPSHOT = {
  workers: { engine: true, delivery: false, scheduler: true, telegram: true },
  queues: [{ name: "deliveries", states: { pending: 3, failed: 1 }, overdue: 2, oldest_pending_seconds: 600 }],
  telegram: [{ channel: "telegram_main", connected: false, error: "Telegram HTTP 401" }],
  mqtt: [{ channel: "mqtt_main", connected: false, attempted: false, error: null }],
  recent_failures: [{ queue: "provider", channel: "telegram_main", attempts: 5, notification_id: "ntf failure",
    error: "<script>unsafe()</script>", created_at: "2026-11-14T10:00:00Z" }],
};

function serve(getBody) {
  globalThis.fetch = async () => ({ ok: true, status: 200, headers: { get: () => "application/json" },
    json: async () => getBody() });
  window.fetch = globalThis.fetch;
}

test("operations shows worker failures, overdue queues and escaped provider errors", async () => {
  setLang("en");
  serve(() => SNAPSHOT);
  try {
    mount(html`<${OperationsView} />`);
    await flush(150);
    assert.match(document.body.textContent, /Delivery: Stopped/);
    assert.match(document.body.textContent, /Telegram HTTP 401/);
    assert.match(document.body.textContent, /Not used yet/);
    assert.match(document.body.textContent, /<script>unsafe\(\)<\/script>/);
    assert.equal(document.querySelector("script"), null);
    assert.ok(document.querySelector('a[href="#/log?id=ntf%20failure"]'));
    assert.deepEqual(await nameViolations(), []);
  } finally { unmount(); }
});

test("operations refreshes snapshots and renders Romanian labels", async () => {
  setLang("ro");
  let snapshot = SNAPSHOT;
  serve(() => snapshot);
  try {
    mount(html`<${OperationsView} />`);
    await flush(150);
    assert.match(document.body.textContent, /Monitorizare/);
    assert.match(document.body.textContent, /Livrare: Oprit/);
    snapshot = { ...SNAPSHOT, workers: { delivery: true }, recent_failures: [] };
    [...document.querySelectorAll("button")].find((b) => b.textContent === "Reîmprospătează").click();
    await flush(150);
    assert.match(document.body.textContent, /Livrare: Activ/);
    assert.match(document.body.textContent, /Nu există eșecuri definitive/);
  } finally { unmount(); setLang("en"); }
});
