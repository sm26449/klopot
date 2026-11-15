// UX-020: creating a template is POST (the type) then PUT (its channel routing).
// When POST succeeded but PUT failed, the drawer stayed in Create mode, so
// pressing Create again re-POSTed the existing type → 409 and the partial create
// could never be finished. The editor now remembers the created type and
// PATCHes (not POSTs) on retry, so the routing can be saved.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();

function okJson(body) {
  return { ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body) };
}
function errJson(status) {
  return { ok: false, status,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => ({ detail: { code: "INTERNAL", message: "boom" } }), text: async () => "boom" };
}
function typeInto(el, v) { el.value = v; el.dispatchEvent(new window.Event("input", { bubbles: true })); }
const byText = (sel, re) => [...document.querySelectorAll(sel)].find((b) => re.test(b.textContent.trim()));

test("a failed routing PUT after a successful create is recoverable without a 409", async () => {
  const calls = [];
  let putCount = 0;
  globalThis.fetch = async (url, opts) => {
    const method = (opts && opts.method) || "GET";
    const u = String(url);
    calls.push({ method, path: u.split("?")[0] });
    if (u.includes("/v1/channels")) return okJson({ items: [], total: 0 });
    if (u.includes("/v1/templates/foo/channels") && method === "PUT") {
      putCount++;
      return putCount === 1 ? errJson(500) : okJson({});
    }
    if (u.includes("/v1/templates/foo") && method === "PATCH") return okJson({});
    if (u.split("?")[0].endsWith("/v1/templates") && method === "POST") return okJson({ type: "foo" });
    if (u.includes("/v1/templates") && method === "GET") return okJson({ items: [], total: 0 });
    return okJson({});
  };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/templates.js");
  mount(html`<${m.TemplatesView} />`);
  await flush(60);

  byText("button", /new template/i).click();
  await flush(30);
  typeInto(document.getElementById("t-type"), "foo");
  typeInto(document.getElementById("t-title"), "Foo happened");  // required since the client-side checks
  await flush(10);

  // First attempt: POST ok, routing PUT fails → partial create.
  byText("button", /^create$/i).click();
  await flush(40);
  const posts = calls.filter((c) => c.method === "POST" && c.path.endsWith("/v1/templates"));
  assert.equal(posts.length, 1, "the type was created once");
  assert.ok(document.body.textContent.includes("wasn't saved"), "a recovery note is shown");
  assert.ok(byText("button", /^save$/i), "the primary action is now Save, not Create");

  // Retry: must PATCH (not POST again) and succeed.
  calls.length = 0;
  byText("button", /^save$/i).click();
  await flush(40);
  assert.equal(calls.filter((c) => c.method === "POST" && c.path.endsWith("/v1/templates")).length, 0,
    "retry must not re-POST the already-created type (would 409)");
  assert.ok(calls.some((c) => c.method === "PATCH" && c.path.endsWith("/v1/templates/foo")),
    "retry PATCHes the existing type");
  assert.equal(putCount, 2, "the routing PUT was retried");
  unmount();
});
