// V18: a dialog whose onClose starts undefined and becomes a real callback
// later — like the "copy this key" modal, whose close is enabled only after
// "I have saved…" is ticked — kept Escape wired to the stale undefined, so
// Escape did nothing even once closing was allowed. useDialog must call the
// CURRENT onClose (via a ref), without remounting the focus trap each render.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { useState, useRef } = await import("../../app/admin_ui/static/lib/h.js");
const { useDialog } = await import("../../app/admin_ui/static/lib/dialog.js");

function pressEscape() {
  window.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
}

test("Escape invokes the onClose that is current, not the one at open time", async () => {
  let closed = 0;
  const onClose = () => { closed++; };

  // Mirrors PlaintextModal: closing is blocked until `saved` is ticked, at
  // which point a real onClose is passed in place of undefined.
  function TestDialog() {
    const [saved, setSaved] = useState(false);
    const ref = useRef(null);
    useDialog(true, saved ? onClose : undefined, ref);
    return html`<div ref=${ref} role="dialog">
      <button class="enable" onClick=${() => setSaved(true)}>I have saved</button>
    </div>`;
  }

  mount(html`<${TestDialog} />`);
  await flush(30);

  // Before enabling: Escape must be a no-op (nothing to close yet).
  pressEscape();
  await flush(10);
  assert.equal(closed, 0, "Escape closed the dialog before it was allowed");

  // Tick "saved" → a real onClose is now passed.
  document.querySelector(".enable").click();
  await flush(30);

  // Escape must now call the CURRENT onClose.
  pressEscape();
  await flush(10);
  assert.equal(closed, 1, "Escape did not invoke the now-current onClose");

  unmount();
});
