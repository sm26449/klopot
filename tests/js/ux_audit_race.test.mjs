// UX-008: a slow earlier Audit response overwrote the newer filter — typing
// actor "a" then "ab", with the "a" response delayed, left the input showing
// "ab" but the table showing "a". Audit now loads through useLoader
// (debounce + abort + generation guard), so only the latest filter's rows show.
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
const rowsFor = (actor) => ({
  items: actor ? [{ id: actor, ts: "2026-11-10T08:00:00Z", actor_kind: "user",
    actor_name: actor, action: "x", resource_kind: "", resource_id: "" }] : [],
  total: actor ? 1 : 0, offset: 0, limit: 50,
});
function typeInto(el, v) { el.value = v; el.dispatchEvent(new window.Event("input", { bubbles: true })); }

test("a late response for an older filter does not overwrite the current rows", async () => {
  const deferred = {};
  globalThis.fetch = async (url) => {
    const u = new URL(String(url), "http://testserver");
    if (!u.pathname.endsWith("/v1/audit")) return okJson({});
    const actor = u.searchParams.get("actor_name") || "";
    if (actor === "a") return new Promise((r) => { deferred.a = () => r(okJson(rowsFor("a"))); }); // slow
    return okJson(rowsFor(actor)); // fast
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/audit.js");
  mount(html`<${m.AuditView} query=${{}} />`);
  await flush(350);

  const actorInput = document.querySelectorAll(".filters input")[3];
  assert.ok(actorInput, "found the actor filter input");

  typeInto(actorInput, "a");
  await flush(350);     // debounce fires → request for actor=a (held open)
  typeInto(actorInput, "ab");
  await flush(350);     // request for actor=ab resolves fast and renders

  deferred.a && deferred.a(); // the stale "a" response finally lands
  await flush(60);

  const bodyText = document.querySelector("table.tbl tbody").textContent;
  assert.match(bodyText, /ab/, "rows for the current filter are shown");
  assert.equal(/\bactor_name/.test(bodyText), false);
  // the row id is the actor; the stale "a"-only row must not be present
  const ids = [...document.querySelectorAll("table.tbl tbody tr")].map((r) => r.textContent);
  assert.ok(ids.every((txt) => txt.includes("ab")), `stale 'a' rows leaked: ${ids.join(" | ")}`);
  unmount();
});
