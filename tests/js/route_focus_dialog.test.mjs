// A route change moves focus to <main> (A36) — but not while a dialog is open:
// a drawer opened by its URL, or the search palette opened before the previous
// route change was rendered, owns focus. Taking it sent the next key (Enter in
// the palette) to the page instead of the dialog.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, until } from "./support/dom.mjs";

const { html } = await setupDom();
const { useRef } = await import("../../app/admin_ui/static/lib/h.js");
const { useDialog, dialogOpen } = await import("../../app/admin_ui/static/lib/dialog.js");
const { focusNewPage } = await import("../../app/admin_ui/static/lib/a11y.js");

function Page({ withDialog }) {
  const ref = useRef(null);
  useDialog(withDialog, () => {}, ref);
  return html`<main id="main-content" tabindex="-1">page</main>
    ${withDialog ? html`<div ref=${ref} role="dialog"><input class="field" /></div>` : null}`;
}

test("a new page takes focus when no dialog is open", async () => {
  window.scrollTo = () => {};
  mount(html`<${Page} withDialog=${false} />`);
  assert.ok(await until(() => document.getElementById("main-content")), "the page rendered");
  assert.equal(dialogOpen(), false);
  focusNewPage();
  assert.equal(document.activeElement?.id, "main-content");
  unmount();
});

test("an open dialog keeps focus through a route change", async () => {
  window.scrollTo = () => {};
  mount(html`<${Page} withDialog=${true} />`);
  assert.ok(await until(() => document.activeElement?.className === "field"), "the dialog focused its field");
  assert.equal(dialogOpen(), true);
  focusNewPage();
  assert.equal(document.activeElement?.className, "field", "the route change left it there");
  unmount();
  assert.ok(await until(() => !dialogOpen()), "closing the dialog leaves the stack");
});
