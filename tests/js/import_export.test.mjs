import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const { TransferMenu, ImportWizard } = await import("../../app/admin_ui/static/lib/transfer.js");
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");

const downloads = [];
window.URL.createObjectURL = () => "blob:test";
window.URL.revokeObjectURL = () => {};
window.HTMLAnchorElement.prototype.click = function click() { downloads.push(this.download); };

const PREVIEW = {
  ok: true, errors: [], warnings: [],
  counts: { new: 1, identical: 1, differs: 2 },
  items: [
    { section: "templates", key: "grid_over", status: "differs", changes: [{ field: "title_template", current: "Over", incoming: "<b>New</b>" }] },
    { section: "rules", key: "r_new", status: "new", changes: [] },
    { section: "rules", key: "r_same", status: "identical", changes: [] },
    { section: "routes", key: "grid_over→tg", status: "differs", changes: [{ field: "severity_min", current: "info", incoming: "warning" }] },
  ],
};

function serve(calls) {
  globalThis.fetch = async (url, init = {}) => {
    const u = new URL(url, "http://testserver");
    calls.push({ path: u.pathname, query: Object.fromEntries(u.searchParams), body: init.body });
    if (u.pathname === "/v1/config/export") {
      return { ok: true, status: 200, headers: { get: () => "application/yaml" }, text: async () => "version: '1.0'\n", json: async () => ({}) };
    }
    let body = {};
    if (u.pathname === "/v1/config/import/preview") body = PREVIEW;
    if (u.pathname === "/v1/config/import/apply") body = { applied: true, ok: true, created: ["rules:r_new"], overwritten: [], skipped: ["templates:grid_over"], copied: { "templates:grid_over": "grid_over_copy" }, errors: [] };
    return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body, text: async () => JSON.stringify(body) };
  };
  window.fetch = globalThis.fetch;
}

const button = (label) => [...document.querySelectorAll("button")].find((b) => b.textContent.trim().startsWith(label));

test("actions menu exports the section, the shown items, and rules with dependencies", async () => {
  setLang("en");
  const calls = [];
  serve(calls);
  try {
    mount(html`<${TransferMenu} section="rules" shownNames=${["a", "b"]} filtered=${true} />`);
    await flush(20);
    button("Actions").click();
    await flush(80);
    assert.deepEqual(await nameViolations(), []);
    button("Export the 2 shown").click();
    await flush(50);
    const q = calls.find((c) => c.path === "/v1/config/export").query;
    assert.deepEqual(q, { mask_secrets: "true", sections: "rules", names: "a,b", with_dependencies: "true" });
    assert.match(downloads.at(-1), /^klopot-rules-filtered-\d{12}\.yaml$/);
    assert.equal(document.querySelector(".menu-panel"), null, "menu closes after export");
  } finally { unmount(); }
});

test("import wizard: preview, default skip, per-item choices, apply payload", async () => {
  setLang("en");
  const calls = [];
  serve(calls);
  let done = 0;
  try {
    mount(html`<${ImportWizard} onClose=${() => {}} onDone=${() => { done++; }} />`);
    await flush(80);
    const ta = document.getElementById("imp-text");
    ta.value = "rules: []\n";
    ta.dispatchEvent(new window.Event("input", { bubbles: true }));
    await flush(20);
    button("Preview").click();
    await flush(80);
    const text = document.body.textContent;
    assert.match(text, /1 new · 2 different · 1 identical/);
    assert.match(text, /<b>New<\/b>/, "incoming values shown as text");
    assert.equal(document.querySelector("ul.diff b b"), null);

    const selects = [...document.querySelectorAll("td select")];
    assert.equal(selects.length, 3, "identical rows have no action");
    const tmpl = selects.find((s) => s.getAttribute("aria-label") === "Action for grid_over");
    assert.equal(tmpl.value, "skip", "existing items default to skip");
    const route = selects.find((s) => s.getAttribute("aria-label") === "Action for grid_over→tg");
    assert.deepEqual([...route.options].map((o) => o.value), ["skip", "overwrite"], "routes cannot be copied");
    tmpl.value = "copy";
    tmpl.dispatchEvent(new window.Event("change", { bubbles: true }));
    const ruleNew = selects.find((s) => s.getAttribute("aria-label") === "Action for r_new");
    assert.equal(ruleNew.value, "import");
    assert.deepEqual(await nameViolations(), []);

    button("Apply").click();
    await flush(80);
    const apply = calls.find((c) => c.path === "/v1/config/import/apply");
    const body = JSON.parse(apply.body);
    assert.deepEqual(body.decisions, { "templates:grid_over": "copy", "routes:grid_over→tg": "skip" });
    assert.equal(body.default_existing, "skip");
    assert.match(document.body.textContent, /templates:grid_over → grid_over_copy/);
    button("Close").click();
    assert.equal(done, 1);
  } finally { unmount(); }
});

test("editing the text after a preview blocks apply until previewed again", async () => {
  setLang("en");
  serve([]);
  try {
    mount(html`<${ImportWizard} onClose=${() => {}} onDone=${() => {}} />`);
    await flush(80);
    const ta = document.getElementById("imp-text");
    ta.value = "rules: []\n";
    ta.dispatchEvent(new window.Event("input", { bubbles: true }));
    await flush(20);
    button("Preview").click();
    await flush(80);
    ta.value = "rules: [] # edited\n";
    ta.dispatchEvent(new window.Event("input", { bubbles: true }));
    await flush(20);
    assert.ok(button("Apply").disabled);
    assert.match(document.body.textContent, /preview again/);
  } finally { unmount(); }
});
