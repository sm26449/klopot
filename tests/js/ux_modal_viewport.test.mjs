// UX-021: the modal (e.g. "What's new") had no height cap or own scroll, so on
// a short/landscape viewport it overflowed off-screen. It must cap to the
// overlay's content box and scroll internally, and the overlay must keep clear
// of the safe-area insets.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(
  fileURLToPath(new URL("../../app/admin_ui/static/styles.css", import.meta.url)), "utf8");

test("the modal is height-capped and scrolls internally", () => {
  const m = css.match(/\.modal\s*\{[^}]*\}/);
  assert.ok(m, ".modal rule not found");
  assert.match(m[0], /max-block-size|max-height/, "modal must cap its height");
  assert.match(m[0], /overflow:\s*auto/, "modal must scroll internally");
});

test("the modal overlay clears the safe-area insets", () => {
  const m = css.match(/\.modal-overlay\s*\{[^}]*\}/);
  assert.ok(m, ".modal-overlay rule not found");
  assert.match(m[0], /env\(safe-area-inset/, "overlay padding should respect safe-area insets");
});
