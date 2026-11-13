// UX-010: the cron preview had no abort/guard, so a slow preview for an old
// expression could replace the preview for the one now in the field (type
// "0 21 * * *" then "0 22 * * *" → preview still showed the 21:00 times). The
// effect now aborts and generation-guards, so only the current cron's preview
// is shown.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

function okJson(body) {
  return {
    ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body),
  };
}
function typeInto(el, v) { el.value = v; el.dispatchEvent(new window.Event("input", { bubbles: true })); }
const byText = (sel, re) => [...document.querySelectorAll(sel)].find((b) => re.test(b.textContent));

test("a late preview for an old cron does not overwrite the current one", async () => {
  const deferred = {};
  globalThis.fetch = async (url) => {
    const u = new URL(String(url), "http://testserver");
    if (u.pathname.endsWith("/v1/schedules/preview")) {
      const cron = u.searchParams.get("cron") || "";
      const body = cron.includes("21")
        ? { next: ["2026-11-10T21:00:00Z"], tz: "ZONE-21" }
        : { next: ["2026-11-10T22:00:00Z"], tz: "ZONE-22" };
      if (cron.includes("21")) return new Promise((r) => { deferred.old = () => r(okJson(body)); });
      return okJson(body);
    }
    if (/\/v1\/(schedules|templates)$/.test(u.pathname)) return okJson({ items: [], total: 0 });
    return okJson({});
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/schedules.js");
  mount(html`<${m.SchedulesView} />`);
  await flush(60);

  // Open the new-schedule drawer; it defaults the cron to "0 21 * * *".
  byText("button", /new schedule/i).click();
  await flush(350); // debounce → preview request for "0 21 * * *" (held open)

  const cronInput = document.getElementById("s-cron");
  assert.ok(cronInput, "cron input is shown");
  typeInto(cronInput, "0 22 * * *");
  await flush(350); // preview for "0 22 * * *" resolves and renders

  deferred.old && deferred.old(); // the stale "21" preview finally lands
  await flush(60);

  const out = document.querySelector(".preview-out");
  assert.ok(out, "a preview is shown");
  assert.match(out.textContent, /ZONE-22/, "preview matches the current cron");
  assert.equal(/ZONE-21/.test(out.textContent), false, "stale preview did not leak");
  unmount();
});
