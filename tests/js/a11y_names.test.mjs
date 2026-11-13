// V13: every admin-UI form control must have a programmatic accessible name —
// a screen reader must be able to say what each field/select/checkbox is. This
// renders the real vendored-preact views and editors in jsdom and runs axe-core,
// asserting zero accessible-NAME violations (label, select-name, aria-*-name,
// button/link-name). A visible label sitting next to a control, with no
// for/id association, does NOT satisfy this — axe (and a screen reader) ignore it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const form = await import("../../app/admin_ui/static/lib/form.js");

function fmt(violations) {
  return violations.flatMap((v) => v.nodes.map((n) => `[${v.id}] ${n.slice(0, 120)}`)).join("\n");
}

async function expectClean(label) {
  const v = await nameViolations();
  assert.equal(v.length, 0, `${label} has accessible-name violations:\n${fmt(v)}`);
}

// ── Metadata-driven form primitives ────────────────────────────────
test("FieldInput variants have accessible names", async () => {
  for (const t of ["string", "int", "float", "bool", "text", "json"]) {
    mount(html`<${form.FieldInput} field=${{ name: "x_" + t, type: t, required: true }} value=${null} onInput=${() => {}} />`);
    await flush(15);
    await expectClean(`FieldInput ${t}`);
    unmount();
  }
  mount(html`<${form.FieldInput} field=${{ name: "sev", type: "select", options: ["a", "b"] }} value=${null} onInput=${() => {}} />`);
  await flush(15);
  await expectClean("FieldInput select");
  unmount();
});

test("SecretField and TagInput have accessible names", async () => {
  for (const status of [undefined, "literal"]) {
    mount(html`<${form.SecretField} field=${{ name: "token", ref_field: "token_ref" }} status=${status} onChange=${() => {}} />`);
    await flush(15);
    await expectClean(`SecretField ${status ?? "unset"}`);
    unmount();
  }
  mount(html`<${form.TagInput} inputId="tg" ariaLabel="Tags" value=${["a"]} onChange=${() => {}} options=${["a", "b"]} />`);
  await flush(15);
  await expectClean("TagInput");
  unmount();
});

// ── Views: list + filters, then the editor opened via its "New" button ──
const VIEWS = [
  ["templates", "TemplatesView", /new template/i],
  ["channels", "ChannelsView", /new channel|add channel/i],
  ["inputs", "InputsView", /new input|add input/i],
  ["variables", "VariablesView", /new variable|add variable/i],
  ["rules", "RulesView", /new rule|add rule/i],
  ["schedules", "SchedulesView", /new schedule|add schedule/i],
  ["snooze", "SnoozeView", null],
  ["apikeys", "ApiKeysView", /new key|create key|new api/i],
  ["log", "LogView", null],
  ["state", "StateView", null],
  ["audit", "AuditView", null],
];

for (const [mod, name, newBtn] of VIEWS) {
  test(`${name} controls are accessible (list${newBtn ? " + editor" : ""})`, async () => {
    const m = await import(`../../app/admin_ui/static/views/${mod}.js`);
    const props = (mod === "log" || mod === "audit") ? { query: {} } : {};
    mount(html`<${m[name]} ...${props} />`);
    await flush(450);
    await expectClean(`${name} (list)`);
    if (newBtn) {
      const btn = [...document.querySelectorAll("button")].find((b) => newBtn.test(b.textContent || ""));
      assert.ok(btn, `${name}: could not find the "new" button to open the editor`);
      btn.click();
      await flush(450);
      await expectClean(`${name} (editor)`);
    }
    unmount();
  });
}
