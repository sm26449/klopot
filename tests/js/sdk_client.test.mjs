import { test } from "node:test";
import assert from "node:assert/strict";
import { createClient, KlopotError } from "../../sdk/typescript/src/index.js";

function fakeFetch(calls, { status = 202, body = { id: "ntf_1", episode: "opened" } } = {}) {
  return async (url, init) => {
    calls.push({ url, ...init, json: init.body ? JSON.parse(init.body) : undefined });
    return { ok: status < 300, status, text: async () => JSON.stringify(body) };
  };
}

test("fire and resolve send the documented request", async () => {
  const calls = [];
  const klopot = createClient({ baseUrl: "https://alerts.example/", apiKey: "alertd_k", fetch: fakeFetch(calls) });
  const res = await klopot.fire("disk_full", { host: "nas" }, { idempotency_key: "nas-disk" });
  assert.equal(res.episode, "opened");
  assert.equal(calls[0].url, "https://alerts.example/v1/fire");
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].headers["X-API-Key"], "alertd_k");
  assert.deepEqual(calls[0].json, { type: "disk_full", context: { host: "nas" }, idempotency_key: "nas-disk" });
  await klopot.resolve("disk_full", "nas-disk");
  assert.deepEqual(calls[1].json, { type: "disk_full", context: {}, idempotency_key: "nas-disk", status: "resolved" });
});

test("API errors raise KlopotError with status and detail", async () => {
  const klopot = createClient({ baseUrl: "https://a", apiKey: "x",
    fetch: fakeFetch([], { status: 401, body: { detail: "Invalid API key" } }) });
  await assert.rejects(klopot.fire("t"), (e) => e instanceof KlopotError && e.status === 401 && /Invalid API key/.test(e.message));
  assert.throws(() => createClient({}), TypeError);
});
