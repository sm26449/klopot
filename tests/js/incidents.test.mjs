import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const { IncidentsView } = await import("../../app/admin_ui/static/views/incidents.js");
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");
setLang("en");

const INITIAL = {
  id: "inc_test", title: "Temperature high", rule_name: "thermal", rule_id: 1,
  state: "active", severity: "critical", opened_at: "2026-11-13T10:00:00Z",
  duration_sec: 120, acknowledged_at: null, acknowledged_by: null,
  resolved_at: null, opening_context: { x: 90 }, resolution_context: null,
};

function serve(initial = INITIAL, failure = false) {
  let current = { ...initial };
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    const u = new URL(url, "http://testserver");
    const method = options.method || "GET";
    calls.push({ url: u, method, body: options.body && JSON.parse(options.body) });
    let body, status = 200;
    if (method === "POST") {
      if (u.pathname.endsWith("/ack")) current = { ...current, acknowledged_at: "2026-11-13T10:02:00Z", acknowledged_by: "operator" };
      if (u.pathname.endsWith("/resolve")) current = { ...current, state: "resolved", resolved_at: "2026-11-13T10:03:00Z", resolution_reason: "manual: Device replaced" };
      body = current;
    } else if (u.pathname.endsWith("/incidents/inc_test")) {
      if (failure) { status = 503; body = { detail: "Temporarily unavailable" }; }
      else body = current;
    } else body = { items: [current], total: 1, limit: 50, offset: 0 };
    return { ok: status < 400, status, headers: { get: () => "application/json" }, json: async () => body, text: async () => JSON.stringify(body) };
  };
  window.fetch = globalThis.fetch;
  return calls;
}

test("ack keeps a problem active; manual resolution requires a reason and uses a separate action", async () => {
  const calls = serve();
  try {
    mount(html`<${IncidentsView} query=${{}} />`);
    await flush(450);
    document.querySelector("button.cell-btn").click();
    await flush(150);
    const dialog = () => document.querySelector('[role="dialog"]');
    assert.match(dialog().textContent, /Active/);
    assert.match(dialog().querySelector('a[href^="#/log"]').getAttribute("href"), /incident=inc_test/);
    assert.deepEqual(await nameViolations('[role="dialog"]'), []);
    const button = (label) => [...dialog().querySelectorAll("button")].find((b) => b.textContent.trim() === label);
    assert.equal(button("Resolve manually").disabled, true);
    button("Acknowledge").click();
    await flush(150);
    assert.match(dialog().textContent, /Active/);
    assert.match(dialog().textContent, /operator/);
    assert.equal(calls.filter((c) => c.method === "POST").length, 1);
    assert.equal(calls.filter((c) => c.method === "POST")[0].url.pathname, "/v1/incidents/inc_test/ack");
    const reason = dialog().querySelector("textarea");
    reason.value = "Device replaced";
    reason.dispatchEvent(new Event("input", { bubbles: true }));
    await flush(30);
    button("Resolve manually").click();
    await flush(150);
    const resolution = calls.find((c) => c.url.pathname.endsWith("/resolve"));
    assert.deepEqual(resolution.body, { reason: "Device replaced" });
    assert.match(dialog().textContent, /Resolved/);
    assert.match(dialog().textContent, /operator/);
  } finally { unmount(); }
});

test("All states is selectable and does not accidentally restore the default active filter", async () => {
  const calls = serve();
  try {
    mount(html`<${IncidentsView} query=${{}} />`);
    await flush(450);
    const select = document.querySelector('select[aria-label="Filter incidents by state"]');
    select.value = "all";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await flush(400);
    const last = calls.filter((c) => c.url.pathname === "/v1/incidents").at(-1);
    assert.equal(last.url.searchParams.has("state"), false);
    assert.match(window.location.hash, /state=all/);
  } finally { unmount(); }
});

test("a failed deep-link detail offers retry and no incident actions", async () => {
  serve(INITIAL, true);
  try {
    mount(html`<${IncidentsView} query=${{}} params=${{ id: "inc_test" }} />`);
    await flush(450);
    const dialog = document.querySelector('[role="dialog"]');
    assert.ok(dialog);
    assert.match(dialog.textContent, /Retry/);
    assert.doesNotMatch(dialog.textContent, /Resolve manually|Acknowledge/);
  } finally { unmount(); }
});
