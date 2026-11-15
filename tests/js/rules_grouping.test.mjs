import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const { RulesView, groupRules } = await import("../../app/admin_ui/static/views/rules.js");
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");

const TEMPLATES = [
  { type: "t_grid", category: "Grid" }, { type: "t_grid2", category: "grid" },
  { type: "t_batt", category: "Battery" }, { type: "t_none", category: null },
];
const rule = (id, name, template_type, extra = {}) => ({
  id, name, template_type, enabled: true, eval_status: "ok", persist_n: 1, eval_interval_sec: 30,
  fire_count_lifetime: 0, last_fired_at: null, inhibited_by: [], ...extra,
});
const RULES = [
  rule(1, "export_over", "t_grid"), rule(2, "pq_event", "t_grid2", { eval_status: "no_data" }),
  rule(3, "soc_low", "t_batt"), rule(4, "misc", "t_none", { enabled: false }),
];

test("groupRules merges case variants and puts Uncategorized last", () => {
  setLang("en");
  const groups = groupRules(RULES, TEMPLATES);
  assert.deepEqual(groups.map(([label, rs]) => [label, rs.map((r) => r.id)]),
    [["Battery", [3]], ["Grid", [1, 2]], ["Uncategorized", [4]]]);
});

function serve(calls) {
  globalThis.fetch = async (url, init = {}) => {
    const u = new URL(url, "http://testserver");
    calls.push({ path: u.pathname, query: Object.fromEntries(u.searchParams), method: init.method || "GET", body: init.body });
    let body = { items: [], total: 0, limit: 500, offset: 0 };
    if (u.pathname === "/v1/templates") body = { items: TEMPLATES, total: TEMPLATES.length };
    if (u.pathname === "/v1/rules" && !u.searchParams.get("eval_status")) body = { items: RULES, total: RULES.length, limit: 500, offset: 0 };
    if (u.pathname === "/v1/rules/bulk/enabled") body = { updated: [1, 2], unchanged: [], not_found: [] };
    return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body };
  };
  window.fetch = globalThis.fetch;
}

test("rules page: grouped sections, collapse, select a group, bulk disable", async () => {
  setLang("en");
  const calls = [];
  serve(calls);
  try {
    mount(html`<${RulesView} query=${{}} params=${{}} />`);
    await flush(150);
    const heads = [...document.querySelectorAll(".group-toggle")].map((b) => b.textContent.replace(/[▾▸]/g, "").trim());
    assert.deepEqual(heads, ["Battery", "Grid", "Uncategorized"]);
    assert.match(document.body.textContent, /2 rules · 2 enabled/);
    assert.match(document.body.textContent, /1 need attention/);     // pq_event: no data

    const grid = [...document.querySelectorAll(".rule-group")][1];
    grid.querySelector(".group-toggle").click();
    await flush(20);
    assert.equal(grid.querySelector("table"), null, "group collapses");
    assert.equal(grid.querySelector(".group-toggle").getAttribute("aria-expanded"), "false");
    grid.querySelector(".group-toggle").click();
    await flush(20);

    grid.querySelector("th.sel input").click();
    await flush(20);
    assert.match(document.querySelector(".bulk-bar").textContent, /2 selected/);
    assert.equal(document.querySelector(".drawer"), null, "selecting does not open the editor");
    assert.deepEqual(await nameViolations(), []);

    [...document.querySelectorAll(".bulk-bar button")].find((b) => b.textContent === "Disable").click();
    await flush(80);
    const bulk = calls.find((c) => c.path === "/v1/rules/bulk/enabled");
    assert.ok(bulk, "bulk endpoint called");
    assert.deepEqual(JSON.parse(bulk.body), { ids: [1, 2], enabled: false });
    assert.equal(document.querySelector(".bulk-bar"), null, "selection cleared after the action");
  } finally { unmount(); }
});

test("rules page sends category and never_fired filters from the URL", async () => {
  setLang("en");
  const calls = [];
  serve(calls);
  try {
    mount(html`<${RulesView} query=${{ category: "Grid", never_fired: "true" }} params=${{}} />`);
    await flush(150);
    const list = calls.find((c) => c.path === "/v1/rules" && c.query.category);
    assert.equal(list.query.category, "Grid");
    assert.equal(list.query.never_fired, "true");
  } finally { unmount(); }
});
