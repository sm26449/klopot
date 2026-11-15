import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount } from "./support/dom.mjs";

const { html } = await setupDom();
const { RuleStatusBadge } = await import("../../app/admin_ui/static/views/rules.js");
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");

function badge(rule) {
  mount(html`<${RuleStatusBadge} rule=${rule} />`);
  const el = document.querySelector(".badge");
  const out = { text: el.textContent, cls: el.className, title: el.getAttribute("title") || "" };
  unmount();
  return out;
}

test("rule badge separates a failing expression from a rule waiting for data", () => {
  setLang("en");
  const err = badge({ enabled: true, eval_status: "error", last_eval_error: "NameError: x" });
  assert.equal(err.text, "error");
  assert.match(err.cls, /warning/);

  const noData = badge({ enabled: true, eval_status: "no_data", last_eval_error: "missing input: grid.cc_power_w" });
  assert.equal(noData.text, "no data");
  assert.doesNotMatch(noData.cls, /warning/);
  assert.match(noData.title, /grid\.cc_power_w/);

  assert.equal(badge({ enabled: true, eval_status: "ok" }).text, "on");
  assert.equal(badge({ enabled: false, eval_status: "error", last_eval_error: "x" }).text, "off · last error");
  assert.equal(badge({ enabled: false, eval_status: "ok" }).text, "off");
});

test("rule badge is translated", () => {
  setLang("ro");
  try {
    assert.equal(badge({ enabled: true, eval_status: "no_data", last_eval_error: "missing input: a.b" }).text, "fără date");
  } finally { setLang("en"); }
});
