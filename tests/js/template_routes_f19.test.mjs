// Regression for F19: the template editor dropped channel_overrides while
// reading routes and omitted them from the complete-replacement PUT, so
// Save nulled real route overrides; a failed route load was treated as {}
// and could unlink every route. These static guards assert the fix stays:
// overrides are captured on load and re-sent, and routing is never PUT when
// the load failed. (The server-side preserve/replace contract is covered by
// the F02/F03 pytest suites.)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const src = readFileSync(
  fileURLToPath(new URL("../../app/admin_ui/static/views/templates.js", import.meta.url)),
  "utf8",
);

test("routes are captured with channel_overrides on load", () => {
  // The load mapping must carry channel_overrides, not just routed/severity.
  assert.match(src, /routed:\s*true,[^}]*channel_overrides/s);
});

test("the routing PUT body includes channel_overrides", () => {
  assert.match(src, /row\.channel_overrides\s*=\s*r\.channel_overrides/);
});

test("routing is not PUT when the route load failed", () => {
  // Save must guard the PUT with the load-error flag.
  assert.match(src, /if\s*\(\s*routes\s*&&\s*!routesError\s*\)/);
});

test("a failed route load does not silently become an empty route set", () => {
  // The catch must flag the error, never setRoutes({}) (which would unlink all).
  assert.match(src, /\.catch\(\(\)\s*=>\s*\{\s*setRoutes\(null\);\s*setRoutesError\(true\)/);
});
