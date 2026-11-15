// V19: the dashboard showed a "unacked critical" tile counted over the last
// 24h next to an "Unacknowledged criticals" list queried over ALL time, with
// no labels — so a 2-vs-8 discrepancy looked like a bug. Each must state its
// own time window so the two numbers are not read as the same measure.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

test("the dashboard labels the 24h tile and the all-time criticals list", async () => {
  const m = await import("../../app/admin_ui/static/views/dashboard.js");
  mount(html`<${m.DashboardView} health=${{ status: "ok", version: "1.7.0", components: {} }} />`);
  await flush(120);

  const text = document.getElementById("app").textContent;
  // The tile states its 24h window...
  assert.match(text, /unacked critical · 24h/i);
  // ...and the list states it is all-time, so the counts aren't conflated.
  assert.match(text, /Unacknowledged criticals/i);
  assert.match(text, /all time/i);
  unmount();
});
