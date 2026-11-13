// UX-006 (part 2): the manually-loaded views (channels/inputs/snooze/apikeys/
// state/account/dashboard) also showed a stuck spinner on a failed load. They
// now track an error and render the shared ErrorState with a retry. Inputs
// exercises the pattern.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

function okJson(body) {
  return { ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body) };
}
function err(status) {
  return { ok: false, status,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => ({ detail: { code: "INTERNAL", message: "nope" } }), text: async () => "nope" };
}
const INPUT = { id: 1, name: "in1", kind: "mqtt", enabled: true, config: {} };

test("Inputs shows error + retry on a failed load and recovers", async () => {
  let calls = 0;
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.includes("/v1/inputs")) { calls++; return calls === 1 ? err(500) : okJson({ items: [INPUT], total: 1 }); }
    return okJson({});
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/inputs.js");
  mount(html`<${m.InputsView} />`);
  await flush(40);

  const alert = document.querySelector('[role="alert"]');
  assert.ok(alert, "an error state is shown");
  const retry = [...alert.querySelectorAll("button")].find((b) => /retry|reîncear/i.test(b.textContent));
  assert.ok(retry, "a retry button is offered");

  retry.click();
  await flush(40);
  assert.equal(document.querySelector('[role="alert"]'), null, "error cleared after retry");
  assert.ok(document.querySelector(".cards"), "the input cards rendered after retry");
  unmount();
});
