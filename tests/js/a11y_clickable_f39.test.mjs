// F39: list rows/cards that open editors must be keyboard-accessible.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { clickable } from "../../app/admin_ui/static/lib/a11y.js";

test("clickable() exposes focus + role + label and keeps onClick", () => {
  let fired = 0;
  const props = clickable(() => { fired++; }, "Edit thing");
  assert.equal(props.tabindex, "0");
  assert.equal(props.role, "button");
  assert.equal(props["aria-label"], "Edit thing");
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

const VIEWS = ["channels", "inputs", "rules", "variables", "schedules", "templates"];
for (const v of VIEWS) {
  test(`${v} view opens its rows via clickable() (keyboard-accessible)`, () => {
    const src = readFileSync(
      fileURLToPath(new URL(`../../app/admin_ui/static/views/${v}.js`, import.meta.url)),
      "utf8",
    );
    assert.match(src, /clickable\(\(\) => setEditing\(/);
  });
}
