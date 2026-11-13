// Regression for the cancelable-load plumbing (audit A28): api requests
// must forward an AbortController signal to fetch, and a cancelled fetch
// must rethrow AbortError (so useLoader ignores it) rather than being
// wrapped into a spurious "unreachable" network error.
import { test } from "node:test";
import assert from "node:assert/strict";

// Minimal browser globals api.js touches on the GET path.
globalThis.window = { location: { origin: "http://testserver" } };

const { request } = await import("../../app/admin_ui/static/lib/api.js");

function okResponse(payload) {
  return {
    ok: true,
    status: 200,
    headers: { get: (k) => (k === "Content-Type" ? "application/json" : null) },
    json: async () => payload,
  };
}

test("GET forwards the abort signal to fetch", async () => {
  let seen;
  globalThis.fetch = async (_url, init) => { seen = init.signal; return okResponse({ ok: true }); };
  const ac = new AbortController();
  await request("GET", "/v1/rules", { signal: ac.signal });
  assert.equal(seen, ac.signal);
});

test("no signal → fetch init has no signal", async () => {
  let seen = "unset";
  globalThis.fetch = async (_url, init) => { seen = init.signal; return okResponse({ ok: true }); };
  await request("GET", "/v1/rules", {});
  assert.equal(seen, undefined);
});

test("an aborted fetch rethrows AbortError, not a wrapped NETWORK error", async () => {
  globalThis.fetch = async () => { const e = new Error("aborted"); e.name = "AbortError"; throw e; };
  await assert.rejects(
    () => request("GET", "/v1/rules", {}),
    (e) => e.name === "AbortError",
  );
});

test("a real network failure is still wrapped as a NETWORK ApiError", async () => {
  globalThis.fetch = async () => { throw new Error("connection refused"); };
  await assert.rejects(
    () => request("GET", "/v1/rules", {}),
    (e) => e.code === "NETWORK",
  );
});
