// Rules UI/UX review (2026-11-18): the editor's Basic / Advanced tabs, the help
// on every field, the list's duration label and plural, test-fire prefill.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, until, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const { RulesView, persistLabel, advancedInUse, groupRules } = await import("../../app/admin_ui/static/views/rules.js");

function respond(handler) {
  globalThis.fetch = async (url, options = {}) => {
    const r = handler(String(url), options);
    const [status, body] = Array.isArray(r) ? r : [200, r ?? { items: [], total: 0, limit: 50, offset: 0 }];
    return { ok: status < 300, status, headers: { get: () => "application/json" }, json: async () => body };
  };
  window.fetch = globalThis.fetch;
}

test("the list says how long a condition must hold", () => {
  assert.equal(persistLabel({ persist_n: 3, eval_interval_sec: 30 }), "held 1m · every 30s");
  assert.equal(persistLabel({ persist_n: 1, eval_interval_sec: 10 }), "first check · every 10s");
  const [[, rules]] = groupRules([{ name: "a", template_type: "x" }], []);
  assert.equal(rules.length, 1);
});

test("advanced options in use are counted", () => {
  assert.equal(advancedInUse({ sort_order: 100 }), 0);
  assert.equal(advancedInUse({ incident_enabled: true, for_each: { n: ["a"] }, vars_extract: ["x"], inhibited_by: [], sort_order: 5 }), 4);
});

const RULE = { id: 3, name: "hot", template_type: "t", condition_expr: "x > 1", persist_n: 1, eval_interval_sec: 10,
  enabled: true, eval_status: "ok", run_state: "inactive", vars_extract: [], inhibited_by: [], fire_count_lifetime: 4,
  incident_enabled: true, recovery_expr: "x < 1", sort_order: 100, last_true_at: null, last_fired_at: null };

test("two tabs: basic fields and the check section first, the rest on Advanced", async () => {
  const posts = [];
  respond((u, o) => {
    if (o.method === "POST" && u.includes("/eval-now")) { posts.push(u); return { matched: false, context: { x: 0.5 }, consecutive_match_count: 0 }; }
    if (o.method === "PATCH") return [422, { detail: [{ loc: ["body", "recovery_expr"], msg: "invalid expression", type: "value_error" }] }];
    if (u.includes("/transitions") || u.includes("/instances")) return [];
    if (u.match(/\/v1\/rules\/3$/)) return RULE;
    if (u.includes("/v1/rules")) return { items: [RULE], total: 1, limit: 50, offset: 0 };
    return null;
  });
  try {
    mount(html`<${RulesView} query=${{}} />`);
    await flush(450);
    assert.match(document.querySelector(".rule-group .muted.small").textContent, /^1 rule · 1 enabled/);
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "hot").click();
    await until(() => document.getElementById("r-tab-basic"));
    // Basic is shown; Advanced counts the incident in use.
    assert.equal(document.getElementById("r-panel-basic").hidden, false);
    assert.equal(document.getElementById("r-panel-advanced").hidden, true);
    assert.match(document.getElementById("r-tab-advanced").textContent, /Advanced\s*1/);
    assert.ok(document.querySelector(".rule-status .badge"), "status badge in the header");
    // Every field explains itself.
    for (const id of ["r-summary", "r-cond", "r-tmpl"]) {
      const help = document.getElementById(document.getElementById(id).getAttribute("aria-describedby"));
      assert.ok(help && help.textContent.length > 20, `${id} has a help line`);
    }
    assert.match(document.getElementById("r-summary-help").textContent, /shown under the rule's name in the list/);
    // Test fire is prefilled from what the rule sees.
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Fill with live values").click();
    await until(() => document.getElementById("r-testctx").value.includes("0.5"));
    assert.deepEqual(JSON.parse(document.getElementById("r-testctx").value), { x: 0.5 });
    // Arrow keys move between the tabs.
    document.getElementById("r-tab-basic").dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    await flush(30);
    assert.equal(document.getElementById("r-panel-advanced").hidden, false);
    assert.deepEqual(await nameViolations('[role="dialog"]'), []);
    // Back to Basic, save: a rejected advanced field brings its tab back.
    document.getElementById("r-tab-basic").click();
    await flush(30);
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Save").click();
    await until(() => document.getElementById("r-panel-advanced").hidden === false);
    assert.ok(document.querySelector("#r-tab-advanced .badge.critical"), "the tab shows the error");
  } finally { unmount(); }
});
