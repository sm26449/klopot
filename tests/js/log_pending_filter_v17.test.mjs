// V17: the Log status filter offered sent/partial/failed/suppressed but not
// pending — so an operator investigating the delivery queue could not isolate
// the in-flight (deferred / rate-limited / retrying) notifications from the UI,
// even though `pending` is a valid delivery_status the API accepts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

test("the Log status filter offers pending and queries delivery_status=pending", async () => {
  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    return {
      ok: true, status: 200,
      headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
      json: async () => ({ items: [], total: 0, offset: 0, limit: 50 }),
      text: async () => "{}",
    };
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/log.js");
  mount(html`<${m.LogView} query=${{}} />`);
  await flush(450);

  // The status <select> must expose a "pending" option.
  const statusSelect = [...document.querySelectorAll("select")]
    .find((s) => [...s.options].some((o) => o.value === "sent"));
  assert.ok(statusSelect, "found the status filter select");
  const values = [...statusSelect.options].map((o) => o.value);
  assert.ok(values.includes("pending"), `status options missing "pending": ${values.join(",")}`);

  // Selecting it must send delivery_status=pending to the API.
  urls.length = 0;
  statusSelect.value = "pending";
  statusSelect.dispatchEvent(new window.Event("change", { bubbles: true }));
  await flush(450);

  const logQuery = urls.find((u) => u.includes("/v1/log"));
  assert.ok(logQuery, "the log list was re-queried");
  assert.match(logQuery, /delivery_status=pending/);
  unmount();
});
