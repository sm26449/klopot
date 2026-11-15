// Regression for admin-UI colour contrast (audit A26). Parses the theme
// tokens from styles.css and asserts every coloured foreground meets the
// WCAG AA 4.5:1 ratio against the background it is actually painted on.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(
  fileURLToPath(new URL("../../app/admin_ui/static/styles.css", import.meta.url)),
  "utf8",
);

function tokensInBlock(selector) {
  // Grab the first `{ ... }` body after the selector and read --name: #hex.
  const i = css.indexOf(selector);
  assert.ok(i >= 0, `selector not found: ${selector}`);
  const body = css.slice(i + selector.length, css.indexOf("}", i));
  const map = {};
  for (const m of body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) map[m[1]] = m[2];
  return map;
}

function lum(hex) {
  const c = hex.replace("#", "");
  const ch = [0, 2, 4].map((o) => parseInt(c.slice(o, o + 2), 16) / 255);
  const f = (x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4);
  const [r, g, b] = ch.map(f);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const L1 = lum(a), L2 = lum(b);
  return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
}

const PAIRS = [
  ["accent", "accent-soft"],
  ["ok", "ok-soft"],
  ["warn", "warn-soft"],
  ["crit", "crit-soft"],
  // --crit is also TEXT on plain surfaces (.btn.danger, error messages), and
  // it is constant across families (ADR-0002), so it must clear every surface.
  ["crit", "bg"],
  ["crit", "surface"],
  ["crit", "surface-2"],
];

const THEMES = [
  [":root {", "klopot-light"],
  [':root[data-theme="dark"] {', "klopot-dark"],
  // OS-native families (ADR-0002) — same AA pairs as the brand theme.
  [':root[data-theme="macos-light"] {', "macos-light"],
  [':root[data-theme="macos-dark"] {', "macos-dark"],
  [':root[data-theme="win-light"] {', "win-light"],
  [':root[data-theme="win-dark"] {', "win-dark"],
  [':root[data-theme="gnome-light"] {', "gnome-light"],
  [':root[data-theme="gnome-dark"] {', "gnome-dark"],
  [':root[data-theme="kde-light"] {', "kde-light"],
  [':root[data-theme="kde-dark"] {', "kde-dark"],
];

for (const [selector, label] of THEMES) {
  const t = tokensInBlock(selector);
  for (const [fg, bg] of PAIRS) {
    test(`${label}: --${fg} on --${bg} meets 4.5:1`, () => {
      const r = ratio(t[fg], t[bg]);
      assert.ok(r >= 4.5, `${t[fg]} on ${t[bg]} = ${r.toFixed(2)} (< 4.5)`);
    });
  }
  // ADR-0001: body/muted text and the accent as a text colour on surfaces.
  // --placeholder is painted on --surface (the input background), audit V15.
  for (const [fg, bg] of [["text", "surface"], ["text-muted", "surface"], ["text-muted", "surface-2"], ["accent", "surface"], ["accent-text", "accent"], ["placeholder", "surface"]]) {
    test(`${label}: --${fg} on --${bg} meets 4.5:1`, () => {
      const r = ratio(t[fg], t[bg]);
      assert.ok(r >= 4.5, `${t[fg]} on ${t[bg]} = ${r.toFixed(2)} (< 4.5)`);
    });
  }
  // --signal is a non-text "live" indicator (dot, row flash): WCAG 1.4.11 → 3:1.
  for (const bg of ["surface", "bg"]) {
    test(`${label}: --signal on --${bg} meets 3:1 (non-text)`, () => {
      const r = ratio(t.signal, t[bg]);
      assert.ok(r >= 3, `${t.signal} on ${t[bg]} = ${r.toFixed(2)} (< 3)`);
    });
  }
}
