// UX-003: the Log row was a role=button (via clickable()) with an Ack button
// inside it. Activating Ack bubbled a keydown to the row handler, which
// preventDefault()'d the native activation — Enter on Ack opened the drawer and
// never acknowledged (nested-interactive, WCAG 4.1.2). The row is no longer a
// button; Ack is a real button whose activation acks and does NOT open details,
// and a separate cell button opens the drawer.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

const ROW = {
  id: 7, fired_at: "2026-11-10T08:00:00Z", severity: "warning", type: "test.alert",
  title: "Test alert", dispatched_to: ["tg"], failed_channels: {},
  acknowledged_at: null, suppressed_reason: null, status: "sent", delivery_status: "sent",
};

function serve(calls) {
  globalThis.fetch = async (url, opts) => {
    calls.push({ url: String(url), method: (opts && opts.method) || "GET" });
    const body = String(url).includes("/v1/log") && !String(url).includes("/ack") && /\/v1\/log(\?|$)/.test(String(url))
      ? { items: [ROW], total: 1, offset: 0, limit: 50 }
      : String(url).includes(`/v1/log/${ROW.id}`) && !String(url).includes("/ack") ? ROW : {};
    return {
      ok: true, status: 200,
      headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
      json: async () => body, text: async () => JSON.stringify(body),
    };
  };
  globalThis.window.fetch = globalThis.fetch;
}

test("the Log row is not a button, and Ack acknowledges without opening details", async () => {
  const calls = [];
  serve(calls);
  const m = await import("../../app/admin_ui/static/views/log.js");
  mount(html`<${m.LogView} query=${{}} />`);
  await flush(450);

  const row = document.querySelector("table.tbl.log tbody tr");
  assert.ok(row, "a log row rendered");
  assert.equal(row.getAttribute("role"), null, "the row is not role=button (no nested-interactive)");

  // Ack is a real button; activating it posts exactly one /ack and opens no drawer.
  const ackBtn = [...row.querySelectorAll("button")].find((b) => /ack/i.test(b.textContent));
  assert.ok(ackBtn, "the row has an Ack button");
  calls.length = 0;
  ackBtn.click();
  await flush(50);
  const ackPosts = calls.filter((c) => c.method === "POST" && c.url.includes(`/v1/log/${ROW.id}/ack`));
  assert.equal(ackPosts.length, 1, "exactly one ack request");
  assert.equal(document.querySelector('[role="dialog"]'), null, "Ack did not open the detail drawer");

  // The dedicated cell button opens the drawer.
  const details = row.querySelector("button.cell-btn");
  assert.ok(details, "the row has a keyboard-operable details button");
  details.click();
  await flush(50);
  assert.ok(document.querySelector('[role="dialog"]'), "details button opens the drawer");
  unmount();
});
