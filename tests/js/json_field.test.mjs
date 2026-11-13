// Regression tests for the admin-UI JSON field validator (audit A24).
//
// The bug: an invalid JSON edit was swallowed — the parent form kept its
// last valid value and Save stayed enabled, so a "saved" confirmation
// could fire while the edited (invalid) text was never persisted
// (browser-final-results.json → invalidJsonSaved=true). The fix reports
// invalid text as such so the editor can block the save.
//
// Run: node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";

import { parseJsonField } from "../../app/admin_ui/static/lib/json_field.js";

test("valid JSON object parses and is marked ok", () => {
  const r = parseJsonField('{"a": 1}');
  assert.equal(r.ok, true);
  assert.deepEqual(r.value, { a: 1 });
});

test("valid JSON array parses", () => {
  const r = parseJsonField("[1, 2, 3]");
  assert.equal(r.ok, true);
  assert.deepEqual(r.value, [1, 2, 3]);
});

test("empty / whitespace clears the field (ok, null value)", () => {
  for (const t of ["", "   ", "\n\t"]) {
    const r = parseJsonField(t);
    assert.equal(r.ok, true, JSON.stringify(t));
    assert.equal(r.value, null);
  }
});

test("null/undefined text is treated as cleared", () => {
  assert.deepEqual(parseJsonField(null), { ok: true, value: null });
  assert.deepEqual(parseJsonField(undefined), { ok: true, value: null });
});

test("A24: invalid JSON is reported invalid, not silently accepted", () => {
  // The exact failure mode: a half-typed object must NOT come back ok,
  // and must carry no `value` the form could persist as the old one.
  const r = parseJsonField('{"a": 1');
  assert.equal(r.ok, false);
  assert.equal("value" in r, false);
  assert.equal(typeof r.error, "string");
});

test("A24: trailing garbage / non-JSON text is invalid", () => {
  for (const t of ['{"a":1} oops', "not json at all", "{a:1}", "[1,2,"]) {
    assert.equal(parseJsonField(t).ok, false, t);
  }
});
