import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush, nameViolations } from "./support/dom.mjs";

const { html } = await setupDom();
const { ApiView, operations, curlFor, typeLabel } = await import("../../app/admin_ui/static/views/api.js");
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");

const SPEC = {
  paths: {
    "/v1/fire": { post: {
      tags: ["fire"], summary: "Fire a notification by type", security: [{ APIKeyHeader: [] }],
      "x-required-scope": "fire",
      description: "Callers post <b>type</b> and context.",
      requestBody: { content: { "application/json": { schema: { $ref: "#/components/schemas/FireRequest" } } } },
      responses: { 202: { description: "Accepted" }, 422: { description: "Validation Error" } },
    } },
    "/v1/rules/{rule_id}": { get: {
      tags: ["rules"], summary: "Get a rule", security: [{ APIKeyHeader: [] }], "x-required-scope": "read",
      parameters: [{ name: "rule_id", in: "path", required: true, schema: { type: "integer" } }],
      responses: { 200: { description: "OK" } },
    } },
    "/v1/auth/password": { post: {
      tags: ["auth"], summary: "Change password", "x-required-scope": "session", responses: { 204: { description: "Changed" } },
    } },
    "/v1/health": { get: { tags: ["health"], summary: "Liveness", responses: { 200: { description: "OK" } } } },
  },
  components: { schemas: { FireRequest: {
    type: "object", required: ["type"],
    properties: {
      type: { type: "string", description: "Template type" },
      context: { type: "object" },
      test: { type: "boolean", default: false },
      severity: { anyOf: [{ type: "string" }, { type: "null" }] },
    },
  } } },
};

function serve(body, status = 200) {
  globalThis.fetch = async () => ({ ok: status < 300, status, headers: { get: () => "application/json" },
    json: async () => body });
  window.fetch = globalThis.fetch;
}

test("operations, type labels and curl are derived from the spec", () => {
  const ops = operations(SPEC);
  assert.deepEqual(ops.map((o) => `${o.method} ${o.path}`),
    ["post /v1/fire", "get /v1/rules/{rule_id}", "post /v1/auth/password", "get /v1/health"]);
  assert.equal(typeLabel({ anyOf: [{ type: "string" }, { type: "null" }] }), "string");
  assert.equal(typeLabel({ type: "array", items: { $ref: "#/components/schemas/X" } }), "X[]");
  const curl = curlFor(SPEC, ops[0], "https://alerts.example");
  assert.match(curl, /curl -X POST 'https:\/\/alerts\.example\/v1\/fire'/);
  assert.match(curl, /X-API-Key: \$KLOPOT_KEY/);
  assert.match(curl, /-d '\{"type":"…"\}'/);
  // A session-only endpoint gets no API-key header; a public one neither.
  assert.doesNotMatch(curlFor(SPEC, ops[2], "h"), /X-API-Key/);
  assert.doesNotMatch(curlFor(SPEC, ops[3], "h"), /X-API-Key/);
});

test("API view groups endpoints, shows scopes, escapes text and filters", async () => {
  setLang("en");
  serve(SPEC);
  try {
    mount(html`<${ApiView} />`);
    await flush(150);
    const text = document.body.textContent;
    assert.match(text, /API reference/);
    assert.match(text, /scope: fire/);
    assert.match(text, /scope: read/);
    assert.match(text, /browser session only/);
    assert.match(text, /no API key/);
    assert.match(text, /<b>type<\/b>/);            // description rendered as text, not HTML
    assert.equal(document.querySelector(".api-desc b"), null);
    assert.ok(document.querySelector('a[href="/docs"]'));
    assert.ok(document.querySelector('a[href="/openapi.json"]'));
    assert.ok(document.querySelector('a[href="#/api-keys"]'));
    assert.equal(document.querySelectorAll(".api-op").length, 4);

    const search = document.querySelector(".filters input");
    search.value = "rule";
    search.dispatchEvent(new window.Event("input", { bubbles: true }));
    await flush(50);
    assert.equal(document.querySelectorAll(".api-op").length, 1);
    assert.deepEqual(await nameViolations(), []);
  } finally { unmount(); }
});

test("API view shows an error with retry when the schema can't be loaded", async () => {
  setLang("ro");
  serve({ detail: "Log in" }, 401);
  try {
    mount(html`<${ApiView} />`);
    await flush(150);
    assert.match(document.body.textContent, /Referință API/);
    assert.ok(document.querySelector(".error-state, [role=alert]"));
  } finally { unmount(); setLang("en"); }
});
