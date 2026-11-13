// UX-017: shared primitives and relative time were hard-coded English even in
// Romanian. The primitives now go through the catalog and dates/relative time
// use Intl with the active locale.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");
const { fmtRelative } = await import("../../app/admin_ui/static/lib/format.js");
const { Empty, Pager, DangerConfirm } = await import("../../app/admin_ui/static/lib/ui.js");
const { SecretField, TagInput } = await import("../../app/admin_ui/static/lib/form.js");

test("relative time uses Intl with the active locale", () => {
  // Node's small-ICU may lack non-English relative-time data, but the browser
  // has it — so assert the mechanism (Intl keyed on the active locale), which
  // holds regardless of the ICU build.
  const past = new Date(Date.now() - 5 * 60000).toISOString();
  try {
    for (const lang of ["en", "ro"]) {
      setLang(lang);
      const n = Math.round((new Date(past).getTime() - Date.now()) / 60000);
      const expected = new Intl.RelativeTimeFormat(lang, { numeric: "auto", style: "narrow" }).format(n, "minute");
      assert.equal(fmtRelative(past), expected, `fmtRelative must use Intl for "${lang}"`);
    }
  } finally { setLang("en"); }
});

test("shared primitives render in the active locale", async () => {
  try {
    setLang("ro");
    mount(html`<div><${Empty} /><${Pager} offset=${0} limit=${50} total=${200} onPage=${() => {}} /></div>`);
    await flush(10);
    const txt = document.getElementById("app").textContent;
    assert.match(txt, /Nimic aici/, "Empty is localized");
    assert.match(txt, /Înainte|Înapoi/, "Pager is localized");
  } finally { setLang("en"); unmount(); }
});

// UX-017 / R7: the secret field's replace/ref/clear text, the tag remove
// aria-label and the typed-confirm prompt were hard-coded English.
test("SecretField renders localized text in replace / ref / clear modes", async () => {
  try {
    setLang("ro");
    const field = { name: "token", ref_field: "token_ref", secret: true };
    // [mode, trigger-label, check(app)] — placeholders aren't in textContent, so
    // the input modes assert on the placeholder attribute.
    const cases = [
      ["value", /Înlocuiește/, () => assert.equal(document.querySelector('input[type="password"]').placeholder, "Valoare secretă nouă")],
      ["ref", /Folosește ref env/, () => {
        assert.equal(document.querySelector('input[type="text"]').placeholder, "NUME_VAR_ENV");
        assert.match(document.getElementById("app").textContent, /variabile de mediu/i);
      }],
      ["clear", /Golește/, () => assert.match(document.getElementById("app").textContent, /Șterge secretul/)],
    ];
    for (const [mode, labelRe, check] of cases) {
      mount(html`<${SecretField} field=${field} status=${mode === "clear" ? "literal" : undefined} onChange=${() => {}} />`);
      await flush(10);
      const btn = [...document.querySelectorAll("button")].find((b) => labelRe.test(b.textContent));
      assert.ok(btn, `the ${mode} trigger is localized`);
      btn.click();
      await flush(10);
      check();
      unmount();
    }
  } finally { setLang("en"); }
});

test("TagInput's remove button has a localized aria-label", async () => {
  try {
    setLang("ro");
    mount(html`<${TagInput} value=${["soc_low"]} onChange=${() => {}} />`);
    await flush(10);
    const x = document.querySelector(".taginput .x");
    assert.match(x.getAttribute("aria-label"), /elimină soc_low/, "remove aria-label is localized + interpolated");
  } finally { setLang("en"); unmount(); }
});

test("DangerConfirm's typed-confirm prompt is localized and keeps the token in a <code>", async () => {
  try {
    setLang("ro");
    mount(html`<${DangerConfirm} open=${true} token=${"my-rule"} title=${"T"} onConfirm=${() => {}} onClose=${() => {}} />`);
    await flush(10);
    const txt = document.getElementById("app").textContent;
    assert.match(txt, /Scrie/, "prompt is localized");
    assert.match(txt, /pentru confirmare/, "prompt suffix is localized");
    const code = document.querySelector(".modal code");
    assert.equal(code.textContent, "my-rule", "the token stays in a <code> element");
  } finally { setLang("en"); unmount(); }
});
