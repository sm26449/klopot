// UX-018 / R8: field-error handling extended — Schedules & API keys gain the
// summary (were toast-only), the summary links each error to its control, and
// the server-rejected control itself gets aria-invalid + an associated message.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { FieldErrorSummary, useFieldErrors, FieldInput, fieldErrorId } =
  await import("../../app/admin_ui/static/lib/form.js");
const { useState } = await import("../../app/admin_ui/static/lib/h.js");

const src = (p) => readFileSync(fileURLToPath(new URL("../../app/admin_ui/static/views/" + p, import.meta.url)), "utf8");

test("msgFor matches a control by the last path segment (nested config.*)", async () => {
  let api;
  function P() { api = useFieldErrors(); return html`<span>${api.errors ? "e" : "-"}</span>`; }
  mount(html`<${P} />`);
  api.show({ status: 422, detail: [
    { loc: ["body", "config", "host"], msg: "invalid host" },
    { loc: ["body", "cron_expr"], msg: "bad cron" },
  ] });
  await flush(10); // let the component re-render so `api` reflects the stored errors
  assert.equal(api.msgFor("host"), "invalid host", "nested config.host matched by segment");
  assert.equal(api.msgFor("cron_expr"), "bad cron");
  assert.equal(api.msgFor("absent"), null);
  unmount();
});

test("a summary entry moves focus to its mapped control", async () => {
  function Harness() {
    // A control the summary should focus, plus the summary pointing at it.
    return html`<div>
      <input id="s-cron" />
      <${FieldErrorSummary} errors=${[{ field: "cron_expr", msg: "bad cron" }]}
        idFor=${(f) => ({ cron_expr: "s-cron" }[f] || "s-cron")} />
    </div>`;
  }
  mount(html`<${Harness} />`);
  await flush(10);
  const btn = document.querySelector(".field-error-summary .link-btn");
  assert.ok(btn, "the entry is a button");
  btn.click(); // focus moves synchronously inside the handler
  assert.equal(document.activeElement, document.getElementById("s-cron"), "focus moved to the control");
  unmount();
});

test("FieldInput marks the server-rejected control invalid and associates the message", async () => {
  mount(html`<${FieldInput} field=${{ name: "host", type: "string" }} value=${""} onInput=${() => {}} error=${"invalid host"} />`);
  await flush(10);
  const input = document.getElementById("f_host");
  assert.equal(input.getAttribute("aria-invalid"), "true", "control is aria-invalid");
  const errId = fieldErrorId("host");
  assert.equal(input.getAttribute("aria-describedby"), errId, "control points at its error");
  const errEl = document.getElementById(errId);
  assert.ok(errEl, "the associated error element exists");
  assert.match(errEl.textContent, /invalid host/);
  assert.equal(errEl.getAttribute("role"), "alert", "announced");
  unmount();
});

test("a FieldInput without a server error carries no aria-invalid", async () => {
  mount(html`<${FieldInput} field=${{ name: "host", type: "string" }} value=${""} onInput=${() => {}} />`);
  await flush(10);
  assert.equal(document.getElementById("f_host").getAttribute("aria-invalid"), null);
  unmount();
});

// The two forms that were toast-only now wire the summary + per-field assoc.
test("Schedules and API keys integrate the field-error summary", () => {
  for (const file of ["schedules.js", "apikeys.js"]) {
    const s = src(file);
    assert.match(s, /useFieldErrors/, `${file} uses the hook`);
    assert.match(s, /\$\{FieldErrorSummary\}/, `${file} renders the summary`);
    assert.match(s, /if\s*\(!fe\.show\(e\)\)\s*toast\.error\(e\)/, `${file} shows 422s in the summary, toasts the rest`);
    assert.match(s, /fe\.msgFor\(/, `${file} associates at least one field`);
    assert.match(s, /fieldErrorId\(/, `${file} ties the control to its message`);
  }
});

test("Rules associates its hand-written fields with server errors", () => {
  const s = src("rules.js");
  assert.match(s, /fieldErrs\.msgFor\("condition_expr"\)/, "the expression field is associated");
  assert.match(s, /idFor=\$\{\(f\)/, "the summary maps field paths to control ids");
});
