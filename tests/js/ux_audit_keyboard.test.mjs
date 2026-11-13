// UX-002: an Audit row was openable only by mouse (<tr onClick>), so a
// keyboard/screen-reader user could not open the before/after snapshot
// (WCAG 2.1.1). The row now carries a real, named button in a cell; a button is
// natively keyboard-operable and keeps the table semantics intact.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

const ENTRY = {
  id: 1, ts: "2026-11-10T08:00:00Z", actor_kind: "user", actor_name: "admin",
  action: "rule.update", resource_kind: "rule", resource_id: "5",
  before: { threshold: 42 }, after: { threshold: 43 },
};

function serve(body) {
  globalThis.fetch = async (url) => ({
    ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => (String(url).includes("/v1/audit") ? body : {}),
    text: async () => JSON.stringify(body),
  });
  globalThis.window.fetch = globalThis.fetch;
}

test("an Audit row's details trigger is a named, keyboard-operable button", async () => {
  serve({ items: [ENTRY], total: 1, offset: 0, limit: 50 });
  const m = await import("../../app/admin_ui/static/views/audit.js");
  mount(html`<${m.AuditView} query=${{}} />`);
  await flush(450);

  const trigger = document.querySelector("table.tbl tbody button.cell-btn");
  assert.ok(trigger, "the row has a real <button> trigger (not a click-only <tr>)");
  assert.equal(trigger.tagName, "BUTTON", "trigger is a native button → keyboard-operable");
  assert.ok((trigger.getAttribute("aria-label") || "").length > 0, "trigger has an accessible name");

  // No dialog yet; activating the button opens the snapshot drawer.
  assert.equal(document.querySelector('[role="dialog"]'), null);
  trigger.click();
  await flush(50);
  assert.ok(document.querySelector('[role="dialog"]'), "activating the button opens the detail drawer");
  unmount();
});
