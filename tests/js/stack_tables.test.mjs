// Phone tables (lib/stack_tables.js): a list table becomes one card per row on
// a narrow screen; each cell shows its column name from the header. The labels
// and the table roles are set from the DOM, so no view has to repeat them.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom } from "./support/dom.mjs";

await setupDom();
const { labelTable, stackTables } = await import("../../app/admin_ui/static/lib/stack_tables.js");

function table(html, cls = "tbl") {
  const host = document.createElement("div");
  host.innerHTML = `<table class="${cls}">${html}</table>`;
  document.body.appendChild(host);
  return host.querySelector("table");
}

test("cells get their column's label and the table keeps its roles", () => {
  const t = table(`<thead><tr><th>Fired</th><th>Sev</th><th><span class="sr-only">Actions</span></th></tr></thead>
    <tbody><tr><td>2 min</td><td>Critical</td><td><button>Ack</button></td></tr></tbody>`);
  labelTable(t);
  const cells = [...t.querySelectorAll("tbody td")];
  assert.deepEqual(cells.map((c) => c.dataset.label), ["Fired", "Sev", ""], "an actions column has no visible label");
  assert.ok(t.classList.contains("stacked"));
  assert.equal(t.getAttribute("role"), "table");
  assert.equal(t.querySelector("tbody tr").getAttribute("role"), "row");
  assert.equal(cells[0].getAttribute("role"), "cell");
  assert.equal(t.querySelector("th").getAttribute("role"), "columnheader");
});

test("colspan is followed, and a view's own data-label wins", () => {
  const t = table(`<thead><tr><th colspan="2">Device</th><th>On</th></tr></thead>
    <tbody><tr><td>iPhone</td><td data-label="Service">fcm</td><td>✓</td></tr></tbody>`);
  labelTable(t);
  assert.deepEqual([...t.querySelectorAll("tbody td")].map((c) => c.dataset.label), ["Device", "Service", "On"]);
});

test("matrix and compact tables, and tables without a header, are left alone", () => {
  for (const cls of ["tbl routing", "tbl diff", "tbl compact"]) {
    const t = table(`<thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody>`, cls);
    labelTable(t);
    assert.equal(t.classList.contains("stacked"), false, cls);
  }
  const bare = table(`<tbody><tr><th>Key</th><td>v</td></tr></tbody>`);
  labelTable(bare);
  assert.equal(bare.classList.contains("stacked"), false);
});

test("rows rendered later are labelled too", async () => {
  const root = document.createElement("div");
  document.body.appendChild(root);
  const stop = stackTables(root);
  root.innerHTML = `<table class="tbl"><thead><tr><th>Name</th></tr></thead><tbody></tbody></table>`;
  await new Promise((r) => setTimeout(r, 30));
  root.querySelector("tbody").insertAdjacentHTML("beforeend", "<tr><td>later</td></tr>");
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(root.querySelector("tbody td").dataset.label, "Name");
  stop();
});
