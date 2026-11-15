// F39: list rows/cards that open editors must be keyboard-accessible.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { clickable } from "../../app/admin_ui/static/lib/a11y.js";

test("clickable() exposes focus + role + description and keeps onClick", () => {
  let fired = 0;
  const props = clickable(() => { fired++; }, "Edit thing");
  assert.equal(props.tabindex, "0");
  assert.equal(props.role, "button");
  // Name = visible content (WCAG 2.5.3); the action goes to the description.
  assert.equal(props["aria-label"], undefined);
  assert.equal(props["aria-description"], "Edit thing");
  props.onClick();
  assert.equal(fired, 1);
});

test("clickable() activates on Enter and Space, not other keys", () => {
  let fired = 0;
  const props = clickable(() => { fired++; }, "x");
  const ev = (key) => ({ key, preventDefault() {} });
  props.onKeyDown(ev("Enter"));
  props.onKeyDown(ev(" "));
  props.onKeyDown(ev("a"));
  props.onKeyDown(ev("Tab"));
  assert.equal(fired, 2);
});

const VIEWS = ["channels", "inputs", "variables", "schedules", "templates"];

// Rules rows hold a selection checkbox, so the row itself is not a button
// (no nested interactive controls): the rule name is a real <button> that
// opens the editor, and a mouse click anywhere on the row still does.
test("rules view opens a rule from a real button (keyboard-accessible)", () => {
  const src = readFileSync(
    fileURLToPath(new URL("../../app/admin_ui/static/views/rules.js", import.meta.url)), "utf8");
  assert.match(src, /<button class="link-btn" onClick=\$\{\(e\) => \{ e\.stopPropagation\(\); onOpen\(r\); \}\}/);
  assert.match(src, /<td class="sel" onClick=\$\{\(e\) => e\.stopPropagation\(\)\}>/);
});
for (const v of VIEWS) {
  test(`${v} view opens its rows via clickable() (keyboard-accessible)`, () => {
    const src = readFileSync(
      fileURLToPath(new URL(`../../app/admin_ui/static/views/${v}.js`, import.meta.url)),
      "utf8",
    );
    assert.match(src, /clickable\(\(\) => (setEditing|onOpen)\(/);
  });
}
