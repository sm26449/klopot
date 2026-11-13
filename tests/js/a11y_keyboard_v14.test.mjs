// V14: Log and API-key rows opened editors/detail via a bare onClick on <tr>,
// which keyboard-only users cannot reach or activate. They must be focusable,
// named, and operable with Enter/Space (the shared clickable() helper). The
// horizontally-scrollable regions (Keys table, State table) must be focusable
// and labelled so a keyboard user can scroll them (WCAG 2.1.1).
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

function withItems(byPath) {
  globalThis.fetch = async (url) => {
    const p = new URL(url, "http://testserver").pathname;
    for (const [frag, body] of Object.entries(byPath)) {
      if (p.endsWith(frag)) return respond(body);
    }
    return respond({ items: [], total: 0 });
  };
  globalThis.window.fetch = globalThis.fetch;
}
function respond(body) {
  return {
    ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body),
  };
}

test("Log detail is keyboard-operable via a real button, not a role=button row (UX-003)", async () => {
  withItems({
    "/v1/log": {
      items: [{
        id: "n_1", title: "Battery low", severity: "warning", type: "battery_low",
        fired_at: "2026-11-09T10:00:00Z", dispatched_to: ["ui"], failed_channels: {},
        acknowledged_at: null, suppressed_reason: null,
      }],
      total: 1, offset: 0, limit: 50,
    },
  });
  const m = await import("../../app/admin_ui/static/views/log.js");
  mount(html`<${m.LogView} query=${{}} />`);
  await flush(450);

  const row = [...document.querySelectorAll("tbody tr")][0];
  assert.ok(row, "a log row rendered");
  // UX-003: the row is NO LONGER role=button — it contained an Ack button, so a
  // button-row was a nested-interactive violation and broke Ack from the
  // keyboard. Detail opens via a dedicated, named button in the cell instead.
  assert.equal(row.getAttribute("role"), null, "the row is not role=button");
  const details = row.querySelector("button.cell-btn");
  assert.ok(details, "the row has a keyboard-operable details button");
  assert.equal(details.tagName, "BUTTON");
  assert.match(details.getAttribute("aria-label") || "", /Battery low/);

  // Activating the button opens the detail drawer (role="dialog" from Drawer).
  details.click();
  await flush(60);
  assert.ok(document.querySelector('[role="dialog"], .drawer'), "it opened the detail drawer");
  unmount();
});

test("API-key rows are keyboard-operable; the table is a focusable labelled region", async () => {
  withItems({
    "/v1/api_keys": {
      items: [{
        id: 7, name: "nodered_prod", key_prefix: "ak_abcd", scopes: ["fire"],
        enabled: true, expires_at: null, last_used_at: null, rotated_from_id: null,
      }],
      total: 1,
    },
  });
  const m = await import("../../app/admin_ui/static/views/apikeys.js");
  mount(html`<${m.ApiKeysView} />`);
  await flush(200);

  const region = document.querySelector(".scroll-x[role='region']");
  assert.ok(region, "the keys table is a region");
  assert.equal(region.getAttribute("tabindex"), "0");
  assert.match(region.getAttribute("aria-label") || "", /key/i);

  const row = [...document.querySelectorAll("tbody tr")][0];
  assert.equal(row.getAttribute("role"), "button");
  assert.equal(row.getAttribute("tabindex"), "0");
  assert.match(row.getAttribute("aria-label") || "", /nodered_prod/);

  row.dispatchEvent(new window.KeyboardEvent("keydown", { key: " ", bubbles: true }));
  await flush(60);
  assert.ok(document.querySelector('[role="dialog"], .drawer'), "Space opened the key editor");
  unmount();
});
