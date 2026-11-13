// UX-014: an alert's "rule #N" link (#/rules/{id}) hit "Not found" because the
// router only had /rules. There's now a /rules/:id route and Rules opens that
// rule's editor from the :id param, fetching it even if it's not on page 1.
import { test } from "node:test";
import assert from "node:assert/strict";
import { matchRoute } from "../../app/admin_ui/static/lib/router.js";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

test("the router matches /rules/:id", () => {
  assert.deepEqual(matchRoute("/rules/:id", "/rules/42"), { id: "42" });
  assert.equal(matchRoute("/rules", "/rules/42"), null);
});

function okJson(body) {
  return { ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body) };
}
const RULE = { id: 5, name: "r_five", template_type: "t", condition_expr: "temp > 1",
  persist_n: 1, eval_interval_sec: 10, enabled: true, severity: "warning", cooldown_sec: 0,
  escalate_after_n: 0, escalate_template_type: "", quiet_hours: null, tags: [], description: "" };

test("Rules opens the deep-linked rule from params.id", async () => {
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (/\/v1\/rules\/5(\?|$)/.test(u)) return okJson(RULE);
    return okJson({ items: [], total: 0 });
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/rules.js");
  mount(html`<${m.RulesView} query=${{}} params=${{ id: "5" }} />`);
  await flush(120);

  const dialog = document.querySelector('[role="dialog"]');
  assert.ok(dialog, "the rule editor opened from the deep link");
  assert.ok(/r_five/.test(dialog.textContent), "it opened the right rule");
  unmount();
});
