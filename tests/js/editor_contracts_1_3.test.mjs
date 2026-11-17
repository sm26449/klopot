// 2026-11-17 UI/UX review: two editor contracts that are hard to mount in
// jsdom, checked on the source like apikey_expiry_f38.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (p) => readFileSync(fileURLToPath(new URL(`../../app/admin_ui/static/${p}`, import.meta.url)), "utf8");

test("UX-03: the key's allowed types are in the unsaved-changes guard and the draft", () => {
  const src = read("views/apikeys.js");
  const fields = src.match(/const fields = \{([^}]*)\}/);
  assert.ok(fields, "one field list feeds useDirty and useDraft");
  for (const f of ["name", "scopes", "enabled", "expires", "grace", "cidrs", "rate", "types"]) {
    assert.match(fields[1], new RegExp(`\\b${f}\\b`), `${f} is guarded`);
  }
  assert.match(src, /useDirty\(fields\)/);
  assert.match(src, /useDraft\("apikeys", [^)]*, fields, dirty\)/);
  assert.match(src, /setTypes\(d\.types \?\? ""\)/, "a restored draft keeps the restriction");
});

test("UX-05: Test fire only for what is saved, once at a time, with the reason translated", () => {
  const src = read("views/templates.js");
  assert.match(src, /const unsaved = \(isNew && !createdType\) \|\| dirty;/);
  assert.match(src, /onClick=\$\{testFire\} disabled=\$\{busy \|\| !ctx \|\| unsaved\}/);
  assert.match(src, /async function testFire\(\) \{[\s\S]*?setBusy\(true\);[\s\S]*?finally \{ setBusy\(false\); \}/);
  assert.match(src, /reasonLabel\(fireResult\.suppressed_reason\)/);
});
