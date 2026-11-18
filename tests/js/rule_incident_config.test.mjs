import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const { RulesView } = await import("../../app/admin_ui/static/views/rules.js");

test("incident configuration is opt-in and saves recovery expression, confirmations and template", async () => {
  const posts = [];
  globalThis.fetch = async (url, options = {}) => {
    if (options.method === "POST") posts.push(JSON.parse(options.body));
    // The template field is a select of existing templates.
    const items = String(url).includes("/v1/templates")
      ? [{ type: "overheat", severity: "critical", icon: "🔥" }, { type: "normal", severity: "info" }] : [];
    const body = { items, total: items.length, limit: 50, offset: 0 };
    return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body };
  };
  window.fetch = globalThis.fetch;
  try {
    mount(html`<${RulesView} query=${{}} />`);
    await flush(450);
    [...document.querySelectorAll("button")].find((b) => /new rule/i.test(b.textContent)).click();
    await flush(100);
    assert.equal(document.querySelector("#r-recovery"), null, "legacy mode is the default");
    const track = [...document.querySelectorAll("label")].find((l) => /Track as an incident/.test(l.textContent)).querySelector("input");
    track.click();
    await flush(50);
    assert.ok(document.querySelector("#r-recovery"));
    assert.deepEqual(await nameViolations('[role="dialog"]'), []);
    const tmpl = document.getElementById("r-tmpl");
    tmpl.value = "overheat";
    tmpl.dispatchEvent(new Event("change", { bubbles: true }));
    for (const [id, value] of [["r-name", "thermal"], ["r-cond", "x > 80"],
                               ["r-recovery", "x < 75"], ["r-recovery-n", "3"]]) {
      const element = document.getElementById(id);
      element.value = value;
      element.dispatchEvent(new Event("input", { bubbles: true }));
    }
    // The recovery template is a select of existing templates too (RL-10).
    const resolved = document.getElementById("r-resolved-tmpl");
    assert.deepEqual([...resolved.options].map((o) => o.value), ["", "normal", "overheat"]);
    resolved.value = "normal";
    resolved.dispatchEvent(new Event("change", { bubbles: true }));
    await flush(30);
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Create").click();
    await flush(100);
    assert.equal(posts.length, 1);
    assert.equal(posts[0].incident_enabled, true);
    assert.equal(posts[0].recovery_expr, "x < 75");
    assert.equal(posts[0].recovery_persist_n, 3);
    assert.equal(posts[0].resolved_template_type, "normal");
    assert.equal(posts[0].template_type, "overheat");
  } finally { unmount(); }
});
