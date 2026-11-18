// Rules review stage 3: persistence as a duration (RL-30), "what if" values
// (RL-31), run state and history (RL-32), hysteresis suggestion (RL-33).
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, until } from "./support/dom.mjs";

const { html } = await setupDom();
const { RulesView, holdToChecks, checksToHold, splitDuration, hysteresisFor } = await import("../../app/admin_ui/static/views/rules.js");

test("a duration becomes checks in a row and back", () => {
  assert.equal(holdToChecks(300, 10), 31);            // 5 min every 10 s
  assert.equal(holdToChecks(0, 10), 1);               // at the first check
  assert.equal(holdToChecks(25, 10), 3);              // rounded down to whole checks
  assert.equal(checksToHold(31, 10), 300);
  assert.deepEqual(splitDuration(300), [5, "min"]);
  assert.deepEqual(splitDuration(7200), [2, "h"]);
  assert.deepEqual(splitDuration(45), [45, "s"]);
  assert.deepEqual(splitDuration(0), [0, "min"]);
});

test("hysteresis is offered for a plain threshold only", () => {
  assert.equal(hysteresisFor("battery.temp > 80"), "battery.temp < 76");
  assert.equal(hysteresisFor("soc <= 20"), "soc > 21");
  assert.equal(hysteresisFor("x > 0"), "x < -1");
  assert.equal(hysteresisFor("v > 2.5"), "v < 2.4");
  assert.equal(hysteresisFor("a > 1 AND b < 2"), null);
  assert.equal(hysteresisFor("contains(s, 'x')"), null);
});

const RULE = {
  id: 7, name: "hot", template_type: "t", condition_expr: "temp > 80", persist_n: 31, eval_interval_sec: 10,
  enabled: true, eval_status: "ok", run_state: "firing", run_state_since: "2026-11-18T10:00:00Z",
  last_true_at: "2026-11-18T10:00:00Z", vars_extract: [], inhibited_by: [], fire_count_lifetime: 2,
};

test("the editor shows the duration, the history and checks other values", async () => {
  const posts = [];
  globalThis.fetch = async (url, options = {}) => {
    const u = String(url);
    let body;
    if (options.method === "POST" && u.includes("/v1/rules/validate")) {
      const sent = JSON.parse(options.body);
      posts.push(sent);
      const temp = sent.context ? sent.context.temp : 85;
      body = { ok: true, result: temp > 80, referenced_vars: [{ name: "temp", live_value: 85, present: true, age_sec: 3 }], unknown_vars: [] };
    } else if (u.includes("/transitions")) {
      body = [{ at: "2026-11-18T10:00:00Z", from_state: "pending", to_state: "firing", detail: null },
              { at: "2026-11-18T09:55:00Z", from_state: "inactive", to_state: "pending", detail: null }];
    } else if (u.match(/\/v1\/rules\/7$/)) {
      body = RULE;
    } else {
      const items = u.includes("/v1/rules") ? [RULE] : [];
      body = { items, total: items.length, limit: 50, offset: 0 };
    }
    return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body };
  };
  window.fetch = globalThis.fetch;
  try {
    mount(html`<${RulesView} query=${{}} />`);
    await flush(450);
    // The list shows the run state.
    assert.ok([...document.querySelectorAll(".badge")].some((b) => b.textContent === "firing"));
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "hot").click();
    await until(() => document.getElementById("r-hold"));
    assert.equal(document.getElementById("r-hold").value, "5");
    assert.equal(document.getElementById("r-hold-unit").value, "min");

    // History, newest first.
    await until(() => document.querySelector("details.history tbody tr"));
    const rows = [...document.querySelectorAll("details.history tbody tr")].map((tr) => tr.children[1].textContent);
    assert.deepEqual(rows, ["pending → firing", "inactive → pending"]);

    // Validate, then try another value.
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Validate").click();
    await until(() => [...document.querySelectorAll("button")].some((b) => b.textContent.trim() === "Try other values"));
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Try other values").click();
    await until(() => document.getElementById("r-whatif"));
    const box = document.getElementById("r-whatif");
    assert.deepEqual(JSON.parse(box.value), { temp: 85 });
    box.value = '{"temp": 70}';
    box.dispatchEvent(new Event("input", { bubbles: true }));
    await flush(20);
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Check with these values").click();
    await until(() => posts.length === 2);
    assert.deepEqual(posts[1].context, { temp: 70 });
    await until(() => document.querySelector(".what-if .badge"));
    assert.match(document.querySelector(".what-if .badge").textContent, /false/);

    // A new interval keeps the duration: 5 min every 30 s = 11 checks.
    const interval = document.getElementById("r-evalint");
    interval.value = "30";
    interval.dispatchEvent(new Event("input", { bubbles: true }));
    await flush(20);
    assert.match(document.querySelector("fieldset.timing .hint").textContent, /11 checks in a row/);
  } finally { unmount(); }
});
