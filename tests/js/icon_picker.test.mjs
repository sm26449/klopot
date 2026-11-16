import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, until, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const { useState } = await import("../../app/admin_ui/static/lib/h.js");
const { IconPicker } = await import("../../app/admin_ui/static/lib/icon_picker.js");
const { isValidIcon, searchIcons, ICON_GROUPS } = await import("../../app/admin_ui/static/lib/icons.js");
const { canonicalCategories } = await import("../../app/admin_ui/static/views/templates.js");
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");

test("validity matches the server rule: emoji yes, text and mojibake no", () => {
  for (const ok of ["", "🚀", "⚠️", "🌡️", "🧑‍🔧", "🇷🇴"]) assert.ok(isValidIcon(ok), ok);
  for (const bad of ["âš¡", "ðŸš¨", "??", "x", "1", "⚡x"]) assert.ok(!isValidIcon(bad), bad);
  for (const g of ICON_GROUPS) for (const [emoji] of g.icons) assert.ok(isValidIcon(emoji), emoji);
});

test("search covers English and Romanian keywords", () => {
  assert.ok(searchIcons("battery").some((i) => i.emoji === "🔋"));
  assert.ok(searchIcons("baterie").some((i) => i.emoji === "🔋"));
  assert.equal(searchIcons("zzzz").length, 0);
});

test("categories are merged case-insensitively under the most used spelling", () => {
  const tpls = [{ category: "Grid" }, { category: "grid" }, { category: "Grid" }, { category: null }, { category: "Battery" }];
  assert.deepEqual(canonicalCategories(tpls), ["Battery", "Grid"]);
});

function Harness({ initial }) {
  const [v, setV] = useState(initial);
  return html`<div><${IconPicker} id="ic" value=${v} onChange=${setV} /><output id="out">${v}</output></div>`;
}

test("picker: open, search, pick, and Escape closes only the palette", async () => {
  setLang("en");
  try {
    mount(html`<${Harness} initial="âš¡" />`);
    await flush(20);
    assert.ok(document.querySelector(".icon-picker .error"), "mojibake flagged");
    assert.equal(document.getElementById("ic").getAttribute("aria-invalid"), "true");

    const choose = [...document.querySelectorAll("button")].find((b) => b.textContent === "Choose…");
    choose.click();
    assert.ok(await until(() => document.activeElement === document.querySelector(".icon-panel input[type=search]")),
      "focus moves into the palette");
    const search = document.querySelector(".icon-panel input[type=search]");
    search.value = "baterie";
    search.dispatchEvent(new window.Event("input", { bubbles: true }));
    await flush(20);
    assert.deepEqual(await nameViolations(), []);
    document.querySelector('.icon-cell[aria-label="battery"]').click();
    await flush(20);
    assert.equal(document.getElementById("out").textContent, "🔋");
    assert.equal(document.querySelector(".icon-panel"), null, "palette closes on pick");
    assert.equal(document.querySelector(".icon-picker .error"), null);

    choose.click();
    assert.ok(await until(() => document.activeElement === document.querySelector(".icon-panel input[type=search]")));
    window.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    assert.ok(await until(() => document.querySelector(".icon-panel") === null), "Escape closes the palette");
    assert.equal(document.getElementById("out").textContent, "🔋");
  } finally { unmount(); }
});

test("the editor accepts exactly the icons the server accepts", async () => {
  // Copilot hygiene #6: "‼" passed the editor and the API answered 422.
  // Verdicts come from app/utils/icons.py (tests/api/test_template_icon_category.py checks them).
  const { readFileSync } = await import("node:fs");
  const cases = JSON.parse(readFileSync(new URL("./support/icon_parity.json", import.meta.url), "utf8"));
  const wrong = cases.filter((c) => isValidIcon(c.icon) !== c.valid).map((c) => `${c.icon} → server says ${c.valid}`);
  assert.deepEqual(wrong, []);
});
