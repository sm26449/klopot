// UX-006 (dashboard refinement): the dashboard loaded every panel in one
// Promise.all, so a single failing endpoint left ALL cards stuck. Each panel now
// loads independently with its own error + retry.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

function okJson(body) {
  return { ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body) };
}
function err(status) {
  return { ok: false, status,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => ({ detail: { code: "INTERNAL", message: "down" } }), text: async () => "down" };
}
const STATS = { dispatched: 5, suppressed: 1, unacked_critical: 0, by_severity: {}, suppressed_by_reason: {}, top_types: [] };

test("one failing panel errors alone; the others load; retry recovers it", async () => {
  let snz = 0;
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.includes("/v1/snooze")) { snz++; return snz === 1 ? err(500) : okJson({ items: [] }); }
    if (u.includes("/v1/log/stats")) return okJson(STATS);
    if (u.includes("/v1/log")) return okJson({ items: [] });
    return okJson({ total: 3 }); // rules/templates/channels/inputs/schedules totals
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/dashboard.js");
  mount(html`<${m.DashboardView} health=${{ status: "ok", version: "1.0", components: {} }} />`);
  await flush(60);

  // Exactly the snoozes panel errored; stats/inventory loaded fine.
  const alerts = document.querySelectorAll('[role="alert"]');
  assert.equal(alerts.length, 1, "only the failing panel shows an error");
  assert.ok(document.querySelector(".tiles .tile"), "the stats tiles still rendered");
  assert.ok(/3/.test(document.querySelector(".grid").textContent), "inventory counts rendered");

  // Retry the failed panel → it recovers, no error left.
  const retry = [...alerts[0].querySelectorAll("button")].find((b) => /retry|reîncear/i.test(b.textContent));
  assert.ok(retry, "the panel offers a retry");
  retry.click();
  await flush(60);
  assert.equal(document.querySelectorAll('[role="alert"]').length, 0, "the panel recovered");
  unmount();
});
