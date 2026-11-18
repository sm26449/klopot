// Rules review RL-28: the condition field completes variable and function
// names; Escape closes the list, not the editor drawer.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, until } from "./support/dom.mjs";

const { html } = await setupDom();
const { completions, cheatRows, EXPR_FUNCTIONS } = await import("../../app/admin_ui/static/lib/expr.js");
const { RulesView } = await import("../../app/admin_ui/static/views/rules.js");

const VARS = ["battery.soc", "battery.temp_avg", "pv.f1_status", "grid.voltage"];

test("completions follow the word before the caret", () => {
  const text = "fresh(\"batt";
  const r = completions(text, text.length, VARS);
  assert.equal(r.start, 7);
  assert.deepEqual(r.items.map((i) => i.label), ["battery.soc", "battery.temp_avg"]);
  // Functions are offered with an opening parenthesis.
  const f = completions("x > 1 AND fr", 12, VARS);
  assert.deepEqual(f.items.map((i) => i.insert), ["fresh("]);
  // Names that contain the word come after the prefix matches.
  assert.deepEqual(completions("volt", 4, VARS).items.map((i) => i.label), ["grid.voltage"]);
  // Nothing for one character, inside numbers, or once a variable is complete.
  assert.deepEqual(completions("b", 1, VARS).items, []);
  assert.deepEqual(completions("x > 12", 6, VARS).items, []);
  assert.deepEqual(completions("battery.soc", 11, VARS).items, []);
});

test("the cheat-sheet has a row per catalog entry plus syntax", () => {
  const rows = cheatRows();
  assert.ok(rows.length > EXPR_FUNCTIONS.length);
  assert.ok(rows.every(([sig, desc]) => sig && desc && !desc.startsWith("rules.")), "every row is translated");
});

test("typing in the condition offers variables; Enter inserts, Escape keeps the drawer", async () => {
  globalThis.fetch = async (url) => {
    const items = String(url).includes("/v1/variables") ? VARS.map((name) => ({ name })) : [];
    const body = { items, total: items.length, limit: 50, offset: 0 };
    return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body };
  };
  window.fetch = globalThis.fetch;
  try {
    mount(html`<${RulesView} query=${{}} />`);
    await flush(450);
    [...document.querySelectorAll("button")].find((b) => /new rule/i.test(b.textContent)).click();
    await flush(100);
    const cond = document.getElementById("r-cond");
    cond.value = "battery.s";
    cond.setSelectionRange(9, 9);
    cond.dispatchEvent(new Event("input", { bubbles: true }));
    await until(() => document.querySelector(".expr-suggest"));
    const options = [...document.querySelectorAll(".expr-suggest [role=option]")];
    assert.deepEqual(options.map((o) => o.querySelector(".mono").textContent), ["battery.soc"]);
    assert.equal(cond.getAttribute("aria-activedescendant"), options[0].id);

    cond.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await until(() => !document.querySelector(".expr-suggest"));
    assert.equal(document.getElementById("r-cond").value, "battery.soc");

    // Open the list again, then Escape: the list closes, the editor stays.
    cond.value = "battery.soc > 20 AND is_";
    cond.setSelectionRange(cond.value.length, cond.value.length);
    cond.dispatchEvent(new Event("input", { bubbles: true }));
    await until(() => document.querySelector(".expr-suggest"));
    await flush(30);
    window.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await until(() => !document.querySelector(".expr-suggest"));
    assert.ok(document.getElementById("r-cond"), "the editor is still open");
  } finally { unmount(); }
});
