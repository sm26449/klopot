// UX-011: a wrong *current password* returns 401 INVALID_CREDENTIALS while the
// session is still valid. The global handler emitted auth:expired for every
// non-login 401, so it logged the user out instead of letting them correct the
// field. The mismatch on /v1/auth/password must NOT end the session; any other
// 401 (incl. a genuinely expired session) still does.
import { test } from "node:test";
import assert from "node:assert/strict";

globalThis.window = { location: { origin: "http://testserver" } };
globalThis.document = { cookie: "" }; // POST reads the CSRF cookie
const { request, on } = await import("../../app/admin_ui/static/lib/api.js");

function resp(status, bodyObj) {
  return {
    ok: status < 300, status,
    headers: { get: (k) => (k === "Content-Type" ? "application/json" : null) },
    json: async () => bodyObj, text: async () => JSON.stringify(bodyObj),
  };
}

test("wrong current password surfaces as 401 and does NOT emit auth:expired", async () => {
  let expired = 0;
  const off = on("auth:expired", () => { expired++; });
  globalThis.fetch = async () =>
    resp(401, { detail: { code: "INVALID_CREDENTIALS", message: "Current password is incorrect" } });

  await assert.rejects(
    () => request("POST", "/v1/auth/password", { body: { current_password: "x", new_password: "y" } }),
    (e) => e.status === 401 && e.code === "INVALID_CREDENTIALS");
  assert.equal(expired, 0, "a password mismatch must not log the user out");
  off();
});

test("a 401 on another endpoint still ends the session", async () => {
  let expired = 0;
  const off = on("auth:expired", () => { expired++; });
  globalThis.fetch = async () =>
    resp(401, { detail: { code: "NOT_AUTHENTICATED", message: "Session expired" } });

  await assert.rejects(() => request("GET", "/v1/rules", {}));
  assert.equal(expired, 1, "a genuine session 401 still emits auth:expired");
  off();
});
