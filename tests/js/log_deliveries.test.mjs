import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const { LogView } = await import("../../app/admin_ui/static/views/log.js");
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");

const ROW = {
  id: "delivery", type: "alarm", title: "Alarm", severity: "critical",
  fired_at: "2026-11-13T08:00:00Z", delivery_status: "sent",
  dispatched_to: ["sms_main"], failed_channels: {},
};
const DELIVERY = {
  id: 1, channel: "sms_main", purpose: "escalation", state: "pending",
  attempts: 2, max_attempts: 5, next_attempt_at: "2026-11-13T08:30:00Z",
  updated_at: "2026-11-13T08:29:00Z", lease_until: null,
  last_error: "sink 503 <script>unsafe()</script>",
};

function serve(getDetails) {
  globalThis.fetch = async (url) => {
    const path = new URL(url, "http://testserver").pathname;
    const body = path === "/v1/log/delivery" ? await getDetails()
      : path === "/v1/log" ? { items: [ROW], total: 1, limit: 50, offset: 0 }
      : { items: [] };
    return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body };
  };
  window.fetch = globalThis.fetch;
}

async function openDetails() {
  mount(html`<${LogView} query=${{}} />`);
  await flush(450);
  document.querySelector("button.cell-btn").click();
  await flush(100);
}

test("delivery details show retries separately from initial success and refresh their outcome", async () => {
  setLang("en");
  let delivery = { ...DELIVERY };
  serve(() => ({ ...ROW, deliveries: [delivery] }));
  try {
    await openDetails();
    let card = document.querySelector(".delivery-card");
    assert.ok(card);
    assert.match(card.textContent, /sms_main/);
    assert.match(card.textContent, /Escalation/);
    assert.match(card.textContent, /Pending/);
    assert.match(card.textContent, /2\s*\/\s*5/);
    assert.match(card.textContent, /Next attempt/);
    assert.match(card.textContent, /sink 503 <script>unsafe\(\)<\/script>/);
    assert.equal(card.querySelector("script"), null, "transport error is escaped as text");
    assert.ok(document.querySelector(".why-row .badge.ok"), "initial notification stays sent");
    assert.deepEqual(await nameViolations('[role="dialog"]'), []);

    delivery = { ...delivery, state: "failed", attempts: 5, next_attempt_at: null };
    [...document.querySelectorAll("button")].find((b) => b.textContent === "Refresh deliveries").click();
    await flush(100);
    card = document.querySelector(".delivery-card");
    assert.match(card.textContent, /Permanently failed/);
    assert.match(card.textContent, /5\s*\/\s*5/);
    assert.doesNotMatch(card.textContent, /Next attempt/);
  } finally { unmount(); }
});

test("cancelled escalation and labels are translated into Romanian", async () => {
  setLang("ro");
  serve(() => ({ ...ROW, deliveries: [{ ...DELIVERY, state: "cancelled", next_attempt_at: null, last_error: null }] }));
  try {
    await openDetails();
    const card = document.querySelector(".delivery-card");
    assert.match(card.textContent, /Escaladare/);
    assert.match(card.textContent, /Anulată/);
    assert.match(card.textContent, /Încercări/);
    assert.doesNotMatch(card.textContent, /Următoarea încercare|Ultima eroare/);
  } finally { unmount(); setLang("en"); }
});

test("historical notifications show an explicit empty delivery state", async () => {
  serve(() => ({ ...ROW, deliveries: [] }));
  try {
    await openDetails();
    assert.equal(document.querySelector(".delivery-card"), null);
    assert.match(document.querySelector('[role="dialog"]').textContent, /No delivery records/);
  } finally { unmount(); }
});

test("Telegram view link opens notification details without acknowledging it", async () => {
  const requests = [];
  serve(() => ({ ...ROW, deliveries: [] }));
  const fetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    requests.push({ url: String(url), method: options?.method || "GET" });
    return fetch(url, options);
  };
  window.fetch = globalThis.fetch;
  try {
    mount(html`<${LogView} query=${{ id: "delivery" }} />`);
    await flush(500);
    assert.ok(document.querySelector('[role="dialog"]'));
    assert.ok(requests.some((r) => new URL(r.url, "http://testserver").pathname === "/v1/log/delivery"));
    assert.ok(requests.every((r) => r.method === "GET"));
  } finally { unmount(); }
});
