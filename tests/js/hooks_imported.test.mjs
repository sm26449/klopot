// Regression for F18: a view used `useEffect` without importing it, so the
// template editor crashed at runtime (ReferenceError) — invisible to
// ruff/pytest. This statically asserts every `useX(...)` hook called in a
// view/lib file is either imported or locally defined in that file.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const base = fileURLToPath(new URL("../../app/admin_ui/static/", import.meta.url));
const files = [
  ...readdirSync(base + "views").map((f) => "views/" + f),
  ...readdirSync(base + "lib").map((f) => "lib/" + f),
].filter((f) => f.endsWith(".js"));

for (const rel of files) {
  test(`${rel}: all hooks used are imported or defined`, () => {
    const src = readFileSync(base + rel, "utf8");
    // Names brought in by any `import { ... } from "..."`.
    const imported = new Set();
    for (const m of src.matchAll(/import\s*\{([^}]*)\}\s*from/g)) {
      for (const name of m[1].split(",")) {
        const n = name.trim().split(/\s+as\s+/).pop().trim();
        if (n) imported.add(n);
      }
    }
    // Hooks defined locally (function useX / const useX = …).
    const local = new Set();
    for (const m of src.matchAll(/(?:function|const)\s+(use[A-Z]\w*)/g)) local.add(m[1]);
    // Hook call sites.
    const used = new Set();
    for (const m of src.matchAll(/\b(use[A-Z]\w*)\s*\(/g)) used.add(m[1]);

    const missing = [...used].filter((h) => !imported.has(h) && !local.has(h));
    assert.deepEqual(missing, [], `${rel} uses un-imported hooks: ${missing.join(", ")}`);
  });
}
