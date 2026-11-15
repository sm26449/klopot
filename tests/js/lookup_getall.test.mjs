// Copilot hygiene #7 / #8: pickers and search load every page (not the first
// 500), and a failed secondary lookup is said once instead of passing for an
// empty list.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom } from "./support/dom.mjs";

await setupDom();
const { getAll } = await import("../../app/admin_ui/static/lib/api.js");
const { lookup } = await import("../../app/admin_ui/static/lib/lookup.js");

function okJson(body) {
  return {
    ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body),
  };
}

test("getAll pages with skip until it has every row", async () => {
  const rows = Array.from({ length: 1234 }, (_, i) => ({ id: i }));
  const asked = [];
  globalThis.fetch = async (url) => {
    const u = new URL(String(url), "http://testserver");
    const skip = Number(u.searchParams.get("skip")), limit = Number(u.searchParams.get("limit"));
    asked.push([skip, limit, u.searchParams.get("enabled")]);
    return okJson({ items: rows.slice(skip, skip + limit), total: rows.length });
  };
  const out = await getAll("/v1/rules", { enabled: "true" });
  assert.equal(out.items.length, 1234);
  assert.equal(out.total, 1234);
  assert.deepEqual(asked, [[0, 500, "true"], [500, 500, "true"], [1000, 500, "true"]]);
});

test("getAll stops at 10 000 rows and reports the real total", async () => {
  let calls = 0;
  globalThis.fetch = async (url) => {
    calls += 1;
    const limit = Number(new URL(String(url), "http://testserver").searchParams.get("limit"));
    return okJson({ items: Array.from({ length: limit }, () => ({})), total: 50000 });
  };
  const out = await getAll("/v1/templates");
  assert.equal(out.items.length, 10000);
  assert.equal(out.total, 50000);
  assert.equal(calls, 20);
});

test("a failed lookup returns the fallback and tells the operator once", async () => {
  const { toast } = await import("../../app/admin_ui/static/lib/toast.js");
  const seen = [];
  const orig = toast.error;
  const origConsole = console.error;
  toast.error = (text) => seen.push(text);
  console.error = () => {};
  try {
    const a = await lookup(Promise.reject(new Error("down")), []);
    const b = await lookup(Promise.reject(new Error("down")), "fallback");
    assert.deepEqual(a, []);
    assert.equal(b, "fallback");
    assert.equal(seen.length, 1, "two failures together → one toast");
    assert.equal(await lookup(Promise.resolve(7), 0), 7);
  } finally {
    toast.error = orig;
    console.error = origConsole;
  }
});
