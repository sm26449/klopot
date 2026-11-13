// F38: the key editor must convert a UTC expiry to local wall-clock for the
// datetime-local input (and back on save), not slice the raw UTC string —
// which shifted the instant by the offset on every save.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const src = readFileSync(
  fileURLToPath(new URL("../../app/admin_ui/static/views/apikeys.js", import.meta.url)),
  "utf8",
);

test("expiry init uses the UTC→local converter, not a raw slice", () => {
  assert.match(src, /toLocalDatetimeInput\(apikey\.expires_at\)/);
  assert.doesNotMatch(src, /apikey\.expires_at\.slice\(0,\s*16\)/);
});

test("the converter accounts for the timezone offset", () => {
  assert.match(src, /getTimezoneOffset\(\)\s*\*\s*60000/);
});
