// UX-009: Config let you Apply a different document than the one you validated.
// An in-flight /validate response re-installed an "ok" plan after the textarea
// had already changed, so typing APPLY imported the new (unvalidated) text. The
// plan is now bound to the exact validated revision: a stale response is
// discarded and Apply is only available for the text that was validated.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

function okJson(body) {
  return {
    ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body),
  };
}
function typeInto(el, value) {
  el.value = value;
  el.dispatchEvent(new window.Event("input", { bubbles: true }));
}
const byText = (sel, re) => [...document.querySelectorAll(sel)].find((b) => re.test(b.textContent));

test("a validate response that lands after an edit does not enable Apply (UX-009)", async () => {
  let releaseValidate;
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push({ url: String(url), body: opts && opts.body, method: (opts && opts.method) || "GET" });
    if (String(url).includes("/config/validate"))
      return new Promise((r) => { releaseValidate = () => r(okJson({ ok: true, errors: [], warnings: [] })); });
    return okJson({});
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/config.js");
  mount(html`<${m.ConfigView} />`);
  await flush(30);

  const ta = document.querySelector("textarea");
  typeInto(ta, "templates: []");
  await flush(10);
  byText("button", /validate/i).click(); // starts the in-flight validate
  await flush(10);

  // Edit the text while validate is in flight, then let the old response land.
  typeInto(ta, "channels: []");
  await flush(10);
  releaseValidate();
  await flush(30);

  // The stale "ok" plan must not install → no Apply affordance.
  assert.equal(byText("button", /^apply$/i), undefined, "Apply must not be available for unvalidated text");
  assert.equal(document.querySelector("input[placeholder]")?.placeholder, undefined,
    "the APPLY confirmation input should not be shown");
  unmount();
});

test("Apply imports exactly the validated revision (UX-009 happy path)", async () => {
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push({ url: String(url), body: opts && opts.body, method: (opts && opts.method) || "GET" });
    if (String(url).includes("/config/validate")) return okJson({ ok: true, errors: [], warnings: [] });
    if (String(url).includes("/config/import")) return okJson({ ok: true, applied: true });
    return okJson({});
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/config.js");
  mount(html`<${m.ConfigView} />`);
  await flush(30);

  typeInto(document.querySelector("textarea"), "templates: []");
  await flush(10);
  byText("button", /validate/i).click();
  await flush(30);

  const applyInput = document.querySelector('input[placeholder]');
  assert.ok(applyInput, "Apply confirmation input is shown for the validated text");
  typeInto(applyInput, "APPLY");
  await flush(10);
  calls.length = 0;
  byText("button", /^apply$/i).click();
  await flush(30);

  const imp = calls.find((c) => c.url.includes("/config/import"));
  assert.ok(imp, "import was sent");
  assert.equal(imp.body, "templates: []", "import carried the validated revision");
  unmount();
});
