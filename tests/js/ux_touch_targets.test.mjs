// UX-019: small controls (buttons, nav, hamburger, tag-remove) were below the
// 44px product touch-target minimum. On a coarse pointer they must get at least
// a 44x44 hit area, without changing the desktop density.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(
  fileURLToPath(new URL("../../app/admin_ui/static/styles.css", import.meta.url)), "utf8");

test("a coarse-pointer block enlarges hit areas to 44px", () => {
  const m = css.match(/@media \(pointer: coarse\)\s*\{[\s\S]*?\n\}/);
  assert.ok(m, "no @media (pointer: coarse) block found");
  assert.match(m[0], /min-height:\s*44px/, "controls should reach 44px min-height");
  assert.match(m[0], /\.nav-toggle[\s\S]*min-width:\s*44px/, "the hamburger needs a 44px min-width");
  assert.match(m[0], /\.chip\.tag \.x/, "the tag-remove hit area should be enlarged");
});

// R9: the drawer close ✕ was 44 tall but ~32 wide, and text/tag inputs were
// ~29–39 tall — both below the 44px target on touch.
test("the drawer close and text/tag inputs reach 44px on coarse pointer", () => {
  const m = css.match(/@media \(pointer: coarse\)\s*\{[\s\S]*?\n\}/);
  assert.ok(m, "no @media (pointer: coarse) block found");
  // The icon-only close gets a 44px-wide hit area, not just tall.
  assert.match(m[0], /\.drawer-head \.btn[\s\S]*?min-width:\s*44px/, "the drawer close needs a 44px min-width");
  // Text-like inputs, selects and textareas reach 44px tall; checkboxes/radios
  // are excluded so the .chk rule still governs them.
  const inputRule = m[0].match(/input:not\(\[type="checkbox"\]\):not\(\[type="radio"\]\)[^}]*\{[^}]*\}/);
  assert.ok(inputRule, "a rule targets text-like inputs/select/textarea");
  assert.match(inputRule[0], /textarea/, "textarea included");
  assert.match(inputRule[0], /select/, "select included");
  assert.match(inputRule[0], /min-height:\s*44px/, "they reach 44px min-height");
});
