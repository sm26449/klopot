// ADR-0005: the rule editor's "For each" field and the instances of a saved
// parametric rule.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, until } from "./support/dom.mjs";

const { html } = await setupDom();
const { RulesView, forEachParts } = await import("../../app/admin_ui/static/views/rules.js");

function respond(handler) {
  globalThis.fetch = async (url, options = {}) => {
    const body = handler(String(url), options) ?? { items: [], total: 0, limit: 50, offset: 0 };
    return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body };
  };
  window.fetch = globalThis.fetch;
}

const input = (id, value) => {
  const el = document.getElementById(id);
  el.value = value;
  el.dispatchEvent(new Event("input", { bubbles: true }));
};

test("forEachParts", () => {
  assert.deepEqual(forEachParts({ inv: ["f1", "f2"] }), ["inv", ["f1", "f2"]]);
  assert.deepEqual(forEachParts(null), ["n", []]);
});

test("a new parametric rule sends for_each, and validate checks it", async () => {
  const posts = [];
  respond((u, o) => {
    if (o.method === "POST") {
      posts.push([u, JSON.parse(o.body)]);
      if (u.includes("/validate")) return { ok: true, result: false, referenced_vars: [], unknown_vars: [] };
      return { id: 9 };
    }
    if (u.includes("/v1/templates")) return { items: [{ type: "pt", severity: "warning" }], total: 1, limit: 50, offset: 0 };
    return null;
  });
  try {
    mount(html`<${RulesView} query=${{}} />`);
    await flush(450);
    [...document.querySelectorAll("button")].find((b) => /new rule/i.test(b.textContent)).click();
    await flush(100);
    const tmpl = document.getElementById("r-tmpl");
    tmpl.value = "pt";
    tmpl.dispatchEvent(new Event("change", { bubbles: true }));
    input("r-name", "ov_active");
    input("r-cond", "ov.{inv}.state > 1");
    input("r-fe-param", "inv");
    const values = document.getElementById("r-fe-values");
    for (const v of ["f1", "f2"]) {
      values.value = v;
      values.dispatchEvent(new Event("input", { bubbles: true }));
      await flush(20);                     // the draft is state: let it render first
      values.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      await flush(20);
    }
    assert.equal(document.querySelector(".for-each .warn-text"), null, "{inv} is used");
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Validate").click();
    await until(() => posts.some(([u]) => u.includes("/validate")));
    assert.deepEqual(posts.find(([u]) => u.includes("/validate"))[1].for_each, { inv: ["f1", "f2"] });
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Create").click();
    await until(() => posts.some(([u]) => u.endsWith("/v1/rules")));
    assert.deepEqual(posts.find(([u]) => u.endsWith("/v1/rules"))[1].for_each, { inv: ["f1", "f2"] });
  } finally { unmount(); }
});

test("a saved parametric rule lists its instances", async () => {
  const RULE = { id: 4, name: "ovp", template_type: "pt", condition_expr: "ov.{n}.state > 1", persist_n: 1,
    eval_interval_sec: 10, enabled: true, eval_status: "ok", vars_extract: [], inhibited_by: [],
    fire_count_lifetime: 0, for_each: { n: ["f1", "f2"] } };
  respond((u) => {
    if (u.includes("/instances")) return [{ instance: "f1", run_state: "firing" }, { instance: "f2", run_state: "no_data", last_eval_error: "missing input: ov.f2.state" }];
    if (u.includes("/transitions")) return [{ at: "2026-11-18T10:00:00Z", from_state: "pending", to_state: "firing", instance: "f1" }];
    if (u.match(/\/v1\/rules\/4$/)) return RULE;
    if (u.includes("/v1/rules")) return { items: [RULE], total: 1, limit: 50, offset: 0 };
    return null;
  });
  try {
    mount(html`<${RulesView} query=${{}} />`);
    await flush(450);
    assert.ok([...document.querySelectorAll(".chip")].some((c) => c.textContent === "×2"));
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "ovp").click();
    await until(() => document.querySelectorAll("details.history").length === 2);
    const rows = [...document.querySelectorAll("details.history")[0].querySelectorAll("tbody tr")].map((tr) => tr.children[0].textContent + ":" + tr.children[1].textContent);
    assert.deepEqual(rows, ["f1:firing", "f2:no data"]);
    assert.match(document.querySelectorAll("details.history")[1].querySelector("tbody td:nth-child(2)").textContent, /^f1 · /);
    assert.equal(document.getElementById("r-fe-param").value, "n");
  } finally { unmount(); }
});

test("a parametric template is grouped by its instances' category and not offered for creation (RC-09)", async () => {
  const { expandedTypes, groupRules } = await import("../../app/admin_ui/static/views/rules.js");
  assert.deepEqual(expandedTypes("audit_{n}", { n: ["a", "b"] }), ["audit_a", "audit_b"]);
  assert.deepEqual(expandedTypes("plain", null), ["plain"]);
  const templates = [{ type: "audit_a", category: "Sensors" }, { type: "audit_b", category: "Sensors" }];
  const groups = groupRules([{ name: "p", template_type: "audit_{n}", for_each: { n: ["a", "b"] } }], templates);
  assert.deepEqual(groups.map(([label]) => label), ["Sensors"]);
  const RULE = { id: 5, name: "pa", template_type: "audit_{n}", condition_expr: "x.{n} > 1", persist_n: 1,
    eval_interval_sec: 10, enabled: true, eval_status: "ok", vars_extract: [], inhibited_by: [],
    fire_count_lifetime: 0, for_each: { n: ["a", "b"] } };
  respond((u) => {
    if (u.includes("/v1/templates")) return { items: [{ type: "audit_a", severity: "info", category: "Sensors" }, { type: "audit_b", severity: "info", category: "Sensors" }], total: 2, limit: 50, offset: 0 };
    if (u.includes("/instances") || u.includes("/transitions")) return [];
    if (u.match(/\/v1\/rules\/5$/)) return RULE;
    if (u.includes("/v1/rules")) return { items: [RULE], total: 1, limit: 50, offset: 0 };
    return null;
  });
  try {
    mount(html`<${RulesView} query=${{}} />`);
    await flush(450);
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "pa").click();
    await until(() => document.getElementById("r-tmpl"));
    const option = [...document.getElementById("r-tmpl").options].find((o) => o.value === "audit_{n}");
    assert.match(option.textContent, /for each: audit_a, audit_b/);
    assert.doesNotMatch(option.textContent, /not a template/);
  } finally { unmount(); }
});
