// UX-001: the skip link must focus the main region in place, not navigate.
// A bare href="#main-content" is parsed by the hash router as a route and shows
// "No screen at /main-content" (WCAG 2.4.1). skipToMain() cancels the default
// navigation and moves focus to #main-content without changing the route.
import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { skipToMain } from "../../app/admin_ui/static/lib/a11y.js";

function withDom() {
  const dom = new JSDOM(
    "<!doctype html><html><body><a id='skip' href='#main-content'>skip</a>" +
    "<main id='main-content' tabindex='-1'>content</main></body></html>",
    { url: "http://testserver/#/rules" });
  globalThis.document = dom.window.document;
  return dom;
}

test("skipToMain focuses #main-content, cancels navigation, keeps the route", () => {
  const dom = withDom();
  let prevented = 0;
  const hashBefore = dom.window.location.hash;

  const ok = skipToMain({ preventDefault: () => { prevented++; } });

  assert.equal(ok, true, "main was found and focused");
  assert.equal(prevented, 1, "default navigation was cancelled");
  assert.equal(dom.window.document.activeElement.id, "main-content",
    "focus moved into the main region");
  assert.equal(dom.window.location.hash, hashBefore, "the route did not change");
});

test("skipToMain is a no-op (no throw) when there is no main region", () => {
  const dom = new JSDOM("<!doctype html><html><body></body></html>");
  globalThis.document = dom.window.document;
  assert.equal(skipToMain({ preventDefault() {} }), false);
});
