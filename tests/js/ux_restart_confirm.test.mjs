// UX-016 / R6: restart/reset are recoverable but side-effecting — they fired a
// POST immediately with no confirmation. They now open a localized ConfirmModal
// that explains what resumes; cancelling sends zero POSTs, confirming sends one.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { ConfirmModal } = await import("../../app/admin_ui/static/lib/ui.js");

function okJson(body) {
  return { ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body) };
}

test("ConfirmModal runs onConfirm only on the primary button, onClose on cancel", async () => {
  let confirmed = 0, closed = 0;
  mount(html`<${ConfirmModal} open=${true} title=${"T"} message=${"msg"}
    onConfirm=${() => confirmed++} onClose=${() => closed++} />`);
  await flush(10);
  const modal = document.querySelector(".modal");
  assert.ok(modal, "modal shown");
  assert.match(modal.textContent, /msg/, "explains the consequence");
  modal.querySelector("button:not(.primary)").click(); // cancel
  assert.equal(confirmed, 0);
  assert.equal(closed, 1, "cancel calls onClose, not onConfirm");
  modal.querySelector("button.primary").click(); // confirm
  assert.equal(confirmed, 1, "confirm runs the action");
  unmount();
});

test("Inputs restart confirms first: cancel → no POST, confirm → exactly one", async () => {
  let restarts = 0;
  globalThis.fetch = async (url, opts) => {
    const u = String(url);
    if (u.endsWith("/v1/inputs/1/restart")) { restarts++; return okJson({ ok: true }); }
    if (u.includes("/v1/inputs")) return okJson({ items: [{ id: 1, name: "in1", kind: "mqtt", enabled: true, config: {}, secret_fields_set: {} }], total: 1 });
    if (u.includes("/v1/meta/kinds")) return okJson({ inputs: { mqtt: { fields: [] } } });
    if (u.includes("/health")) return okJson({ connected: true });
    return okJson({});
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/inputs.js");
  mount(html`<${m.InputsView} />`);
  await flush(50);

  // Open the editor for the existing input.
  document.querySelector(".ch-card").click();
  await flush(20);
  const restartBtn = [...document.querySelectorAll(".editor-actions button")].find((b) => /restart|reporn/i.test(b.textContent));
  assert.ok(restartBtn, "the editor shows a Restart button");

  // Click Restart → a confirm dialog appears, but NO POST yet.
  restartBtn.click();
  await flush(20);
  assert.ok(document.querySelector(".modal"), "a confirmation dialog is shown");
  assert.equal(restarts, 0, "no POST fired before confirming");

  // Cancel → still zero POSTs, dialog gone.
  document.querySelector(".modal button:not(.primary)").click();
  await flush(20);
  assert.equal(restarts, 0, "cancelling the confirmation sends no POST");
  assert.equal(document.querySelector(".modal"), null, "dialog closed on cancel");

  // Restart again, then Confirm → exactly one POST.
  [...document.querySelectorAll(".editor-actions button")].find((b) => /restart|reporn/i.test(b.textContent)).click();
  await flush(20);
  document.querySelector(".modal button.primary").click();
  await flush(30);
  assert.equal(restarts, 1, "confirming sends exactly one POST");
  unmount();
});
