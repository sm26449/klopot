// UX-007: closing an editor with unsaved changes (Esc/overlay/X) must confirm
// first, not silently discard the draft. The Drawer guards every close path when
// `dirty`, and useDirty tracks whether a form changed since it opened.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { Drawer, useDirty } = await import("../../app/admin_ui/static/lib/ui.js");

test("a dirty Drawer confirms before closing; a clean one closes freely", async () => {
  let closed = 0;
  mount(html`<${Drawer} open=${true} title="Edit" dirty=${true} onClose=${() => { closed++; }}>body</${Drawer}>`);
  await flush(10);

  // Declining the confirm keeps it open.
  window.confirm = () => false;
  document.querySelector(".drawer-overlay").click();
  assert.equal(closed, 0, "declining keeps the drawer open");

  // Accepting the confirm closes it (via the X button).
  window.confirm = () => true;
  document.querySelector('.drawer-head button[aria-label]').click();
  assert.equal(closed, 1, "accepting discards and closes");
  unmount();

  // A clean drawer closes without any confirm.
  let closed2 = 0;
  let confirmed = 0;
  window.confirm = () => { confirmed++; return true; };
  mount(html`<${Drawer} open=${true} title="View" dirty=${false} onClose=${() => { closed2++; }}>body</${Drawer}>`);
  await flush(10);
  document.querySelector(".drawer-overlay").click();
  assert.equal(closed2, 1, "a clean drawer closes immediately");
  assert.equal(confirmed, 0, "no confirm for a clean drawer");
  unmount();
});

const { useState } = await import("../../app/admin_ui/static/lib/h.js");

test("useDirty is false initially and true after a change", async () => {
  let setV, dirtyNow;
  function P() {
    const [v, s] = useState({ a: 1 });
    setV = s; dirtyNow = useDirty(v);
    return html`<span>${String(dirtyNow)}</span>`;
  }
  mount(html`<${P} />`);
  await flush(10);
  assert.equal(dirtyNow, false, "clean on open");
  setV({ a: 2 });
  await flush(10);
  assert.equal(dirtyNow, true, "dirty after a change");
  unmount();
});
