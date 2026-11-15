// V16: a boolean config field that defaults to TRUE (e.g. webhook
// auth_required) rendered as an UNCHECKED box, because `!!undefined` is false.
// The operator saw "off" while the backend enforced "on", and had to toggle
// twice to opt out. The checkbox must show the real default, and the editor
// must seed config from the metadata defaults so the chosen policy is explicit.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const form = await import("../../app/admin_ui/static/lib/form.js");

const META = JSON.parse(readFileSync(
  fileURLToPath(new URL("./support/meta_kinds.fixture.json", import.meta.url)), "utf8"));

test("configDefaults seeds non-null defaults, skips secrets and null defaults", () => {
  const out = form.configDefaults([
    { name: "auth_required", type: "bool", default: true },
    { name: "retries", type: "int", default: 3 },
    { name: "url", type: "string", default: null },
    { name: "token", type: "string", secret: true, default: "x" },
  ]);
  assert.deepEqual(out, { auth_required: true, retries: 3 });
});

test("round-trip: webhook metadata seeds auth_required=true explicitly", () => {
  const seeded = form.configDefaults(META.inputs.webhook.fields);
  assert.equal(seeded.auth_required, true, "the enforced policy is sent, not omitted");
});

function checkboxOf(root) {
  return root.querySelector('input[type="checkbox"]');
}

test("a bool field defaulting to true renders CHECKED when unset", async () => {
  mount(html`<${form.FieldInput} field=${{ name: "auth_required", type: "bool", default: true }}
    value=${null} onInput=${() => {}} />`);
  await flush(15);
  assert.equal(checkboxOf(document).checked, true);
  unmount();
});

test("an explicit false value renders UNCHECKED (opt-out is expressible)", async () => {
  mount(html`<${form.FieldInput} field=${{ name: "auth_required", type: "bool", default: true }}
    value=${false} onInput=${() => {}} />`);
  await flush(15);
  assert.equal(checkboxOf(document).checked, false);
  unmount();
});
