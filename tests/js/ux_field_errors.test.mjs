// UX-018: field and mutation errors need a real association + contextual
// recovery, not just a red border and a raw server string. An invalid JSON
// field is now aria-invalid, described, and announced; mutation errors get a
// localized lead by status (403/409/429/5xx/network).
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { FieldInput } = await import("../../app/admin_ui/static/lib/form.js");
const { toast, Toasts } = await import("../../app/admin_ui/static/lib/toast.js");

async function until(cond, timeout = 2000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (cond()) return true; await flush(10); }
  return cond();
}

test("an invalid JSON field is aria-invalid, described and announced", async () => {
  mount(html`<${FieldInput} field=${{ name: "data", type: "json" }} value=${{}}
    onInput=${() => {}} onValidity=${() => {}} />`);
  await flush(10);
  const ta = document.querySelector("textarea");
  ta.value = "{invalid";
  ta.dispatchEvent(new window.Event("input", { bubbles: true }));
  await flush(10);

  assert.equal(ta.getAttribute("aria-invalid"), "true", "textarea marked invalid");
  const errId = ta.getAttribute("aria-describedby");
  assert.ok(errId, "aria-describedby points at the error");
  const errEl = document.getElementById(errId);
  assert.ok(errEl, "the described error element exists");
  assert.equal(errEl.getAttribute("role"), "alert", "the error is announced");
  assert.ok(/invalid/i.test(errEl.textContent), "names the problem without relying on colour");
  unmount();
});

test("toast.error adds a localized contextual lead by status", async () => {
  mount(html`<${Toasts} />`);
  const txt = () => document.querySelector(".toasts")?.textContent || "";
  // Preact subscribes <Toasts> on the next frame; poll instead of a fixed
  // delay (docs/ADMIN_UI.md, Testing) — a toast raised earlier is queued.
  toast.error({ status: 403, message: "x" });
  assert.ok(await until(() => /permission/i.test(txt())), "403 → permission lead");
  toast.error({ status: 409, message: "y" });
  assert.ok(await until(() => /changed since/i.test(txt())), "409 → conflict lead");
  toast.error({ message: "z" }); // no status → network
  assert.ok(await until(() => /network/i.test(txt())), "no status → network lead");
  unmount();
});
