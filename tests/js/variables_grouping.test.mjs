import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const { VariablesView, groupByNamespace, namespaceOf } = await import("../../app/admin_ui/static/views/variables.js");
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");

const v = (id, name, extra = {}) => ({
  id, name, source: "mqtt", input_id: 7, config: {}, enabled: true, description: null,
  last_value: 1, last_value_at: "2026-11-14T10:00:00Z", age_sec: 5, is_stale: false,
  value_state: "fresh", used_by_rules: [], used_by_variables: [], ...extra,
});
const VARS = [
  v(1, "grid.power", { used_by_rules: ["export_over"], used_by_variables: ["pv.net"] }),
  v(2, "grid.limit", { value_state: "missing", last_value: null, age_sec: null, last_value_at: null }),
  v(3, "pv.total", { value_state: "stale", is_stale: true, used_by_rules: ["pv_low"] }),
  v(4, "standalone"),
];

test("namespaces group by the first dot segment; no-namespace last", () => {
  assert.equal(namespaceOf("grid.power.l1"), "grid");
  assert.equal(namespaceOf("x"), "");
  assert.deepEqual(groupByNamespace(VARS).map(([ns, vs]) => [ns, vs.length]), [["grid", 2], ["pv", 1], ["", 1]]);
});

function serve(calls) {
  globalThis.fetch = async (url) => {
    const u = new URL(url, "http://testserver");
    calls.push({ path: u.pathname, query: Object.fromEntries(u.searchParams) });
    let body = { items: [], total: 0 };
    if (u.pathname === "/v1/variables") body = { items: VARS, total: VARS.length, limit: 500, offset: 0 };
    if (u.pathname === "/v1/inputs") body = { items: [{ id: 7, name: "broker", kind: "mqtt" }], total: 1 };
    if (u.pathname === "/v1/meta/kinds") body = { variables: {} };
    return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body };
  };
  window.fetch = globalThis.fetch;
}

test("variables page: collapsed namespace overview with per-group counts", async () => {
  setLang("en");
  serve([]);
  try {
    mount(html`<${VariablesView} query=${{}} />`);
    await flush(150);
    const heads = [...document.querySelectorAll(".var-group .group-toggle")].map((b) => b.textContent.replace(/[▾▸]/g, "").trim());
    assert.deepEqual(heads, ["grid", "pv", "(no namespace)"]);
    assert.equal(document.querySelector(".var-group table"), null, "groups start collapsed");
    const grid = document.querySelector(".var-group");
    assert.match(grid.textContent, /2 variables/);
    assert.match(grid.textContent, /1 no value/);
    assert.match(grid.textContent, /1 unused/);

    grid.querySelector(".group-toggle").click();
    await flush(20);
    assert.match(grid.textContent, /1 rule\(s\) · 1 var\(s\)/);
    assert.match(grid.textContent, /no value/);
    assert.deepEqual(await nameViolations(), []);

    // Open the editor from the row: usage is listed with links.
    grid.querySelector("tbody tr").click();
    await flush(50);
    const ruleLink = document.querySelector('a.chip[href="#/rules?search=export_over"]');
    assert.ok(ruleLink, "link to the rule");
    assert.ok(document.querySelector('a.chip[href="#/variables?search=pv.net"]'), "link to the computed variable");
  } finally { unmount(); }
});

test("an active filter opens every group and rides the query", async () => {
  setLang("en");
  const calls = [];
  serve(calls);
  try {
    mount(html`<${VariablesView} query=${{ state: "missing", used: "false" }} />`);
    await flush(150);
    assert.equal(document.querySelectorAll(".var-group table").length, 3, "all groups open while filtering");
    const q = calls.find((c) => c.path === "/v1/variables").query;
    assert.equal(q.state, "missing");
    assert.equal(q.used, "false");
  } finally { unmount(); }
});
