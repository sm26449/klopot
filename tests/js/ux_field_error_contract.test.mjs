// UX-018 (refinement): a 422 from the server carries per-field pydantic errors.
// fieldErrorsFrom maps detail[].loc → {field,msg}; FieldErrorSummary renders them
// as a focusable, announced summary; useFieldErrors.show handles only 422s so the
// caller still toasts other failures. Editors wire these into save().
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { fieldErrorsFrom, FieldErrorSummary, useFieldErrors } =
  await import("../../app/admin_ui/static/lib/form.js");

test("fieldErrorsFrom maps a 422 detail to field paths (and ignores non-422)", () => {
  const e = { status: 422, detail: [
    { loc: ["body", "name"], msg: "field required" },
    { loc: ["body", "config", "host"], msg: "invalid host" },
  ] };
  assert.deepEqual(fieldErrorsFrom(e), [
    { field: "name", msg: "field required" },
    { field: "config.host", msg: "invalid host" },
  ]);
  assert.equal(fieldErrorsFrom({ status: 500, message: "boom" }), null);
  assert.equal(fieldErrorsFrom({ status: 422, detail: "oops" }), null);
});

test("useFieldErrors.show handles 422s and defers others to the caller", () => {
  // drive the hook through a tiny component
  let api;
  function P() {
    api = useFieldErrors();
    return html`<span>${api.errors ? api.errors.length : "none"}</span>`;
  }
  mount(html`<${P} />`);
  const handled422 = api.show({ status: 422, detail: [{ loc: ["body", "x"], msg: "bad" }] });
  assert.equal(handled422, true, "a 422 is handled");
  const handled500 = api.show({ status: 500, message: "down" });
  assert.equal(handled500, false, "a 500 is left to the caller (toast)");
  unmount();
});

test("FieldErrorSummary is a focusable, announced list of the fields", async () => {
  mount(html`<${FieldErrorSummary} errors=${[{ field: "name", msg: "required" }]} />`);
  await flush(10);
  const box = document.querySelector(".field-error-summary");
  assert.ok(box, "summary rendered");
  assert.equal(box.getAttribute("role"), "alert", "announced");
  assert.equal(box.getAttribute("tabindex"), "-1", "focusable for the move");
  assert.match(box.textContent, /name/, "names the field");
  assert.match(box.textContent, /required/, "shows the message");
  unmount();
});
