// Conditional fields from /v1/meta/kinds (`show_if`): the SMS provider shows
// only its own fields, and saving drops the values of hidden ones.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { setupDom } from "./support/dom.mjs";

setupDom();
const { fieldVisible, visibleConfig } = await import("../../app/admin_ui/static/lib/form.js");
const meta = JSON.parse(readFileSync(fileURLToPath(new URL("./support/meta_kinds.fixture.json", import.meta.url)), "utf8"));
const sms = meta.channels.sms.fields;
const shown = (config) => sms.filter((f) => fieldVisible(f, config, sms)).map((f) => f.name);

test("an unset provider counts as its default (http)", () => {
  const names = shown({});
  assert.ok(names.includes("url") && names.includes("body_template"));
  assert.ok(!names.includes("account_sid") && !names.includes("router_url"));
});

test("each provider shows only its own fields", () => {
  assert.deepEqual(shown({ provider: "twilio" }).filter((n) => !["provider", "phone", "max_chars", "timeout_sec"].includes(n)),
    ["account_sid", "auth_token", "from_number", "api_url"]);
  assert.ok(!shown({ provider: "http" }).includes("api_url"), "Twilio's API origin is not an http-gateway field");
  assert.ok(shown({ provider: "teltonika" }).includes("modem"));
});

test("visibleConfig drops non-secret values of hidden fields", () => {
  const out = visibleConfig({ provider: "twilio", phone: "+1", url: "http://old", method: "POST", account_sid: "AC" }, sms);
  assert.deepEqual(out, { provider: "twilio", phone: "+1", account_sid: "AC" });
});

test("fields without show_if are always visible", () => {
  assert.equal(fieldVisible({ name: "x" }, {}, []), true);
});
