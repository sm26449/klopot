// UX-004: the keyboard focus ring must be an OPAQUE outline, not the
// translucent --focus halo (accent at 40%). Composited over a card the halo
// measured ~1.9:1, below the WCAG 1.4.11 non-text-contrast floor of 3:1 in
// 9/10 themes. ADR-0001 fixes the ring as an opaque 2px var(--accent) outline
// with --focus reserved for a halo only.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(
  fileURLToPath(new URL("../../app/admin_ui/static/styles.css", import.meta.url)), "utf8");

test("no focus outline uses the translucent --focus token", () => {
  assert.equal(css.includes("solid var(--focus)"), false,
    "a focus outline still uses var(--focus); use the opaque var(--accent)");
});

test("the global :focus-visible ring is an opaque accent outline", () => {
  const m = css.match(/:focus-visible\s*\{[^}]*\}/);
  assert.ok(m, ":focus-visible rule not found");
  assert.match(m[0], /outline:\s*2px solid var\(--accent\)/,
    ":focus-visible must use an opaque var(--accent) outline");
});
