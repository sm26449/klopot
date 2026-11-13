// UX-006: a failed list fetch used to leave a permanent spinner or a false
// "empty". useLoader now exposes an error and the view shows a persistent
// ErrorState with a retry that re-fetches and recovers. Audit has a single
// clean loader, so it exercises the path directly.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

function okJson(body) {
  return { ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body) };
}
function err(status) {
  return { ok: false, status,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => ({ detail: { code: "INTERNAL", message: "kaboom" } }), text: async () => "kaboom" };
}
const ENTRY = { id: 1, ts: "2026-11-10T08:00:00Z", actor_kind: "user", actor_name: "admin",
  action: "rule.update", resource_kind: "rule", resource_id: "5" };

test("a failed load shows error + retry (not a stuck spinner or false empty), and retry recovers", async () => {
  let calls = 0;
  globalThis.fetch = async (url) => {
    if (String(url).includes("/v1/audit")) { calls++; return calls === 1 ? err(500) : okJson({ items: [ENTRY], total: 1, offset: 0, limit: 50 }); }
    return okJson({ items: [], total: 0 });
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/audit.js");
  mount(html`<${m.AuditView} query=${{}} />`);
  await flush(60);

  const alert = document.querySelector('[role="alert"]');
  assert.ok(alert, "an error state is shown on load failure");
  assert.ok(/kaboom|load/i.test(alert.textContent), "the error is surfaced");
  const retry = [...alert.querySelectorAll("button")].find((b) => /retry|reîncear/i.test(b.textContent));
  assert.ok(retry, "a retry button is offered");
  assert.equal(document.querySelector("table.tbl"), null, "no table while errored");

  retry.click();
  await flush(60);
  assert.equal(document.querySelector('[role="alert"]'), null, "error cleared after a successful retry");
  assert.ok(document.querySelector("table.tbl"), "the list rendered after retry");
  unmount();
});
