// V21: a disabled rule keeps its last eval error as frozen history, which must
// not be surfaced as a current incident — not in the Rules list's current-error
// banner/badge, and not in the dashboard's "with errors" count. Asserted on the
// view sources so the test stays portable (no DOM/render harness needed).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel) => readFileSync(
  fileURLToPath(new URL(`../../app/admin_ui/static/${rel}`, import.meta.url)), "utf8");

const rules = read("views/rules.js");
const dashboard = read("views/dashboard.js");
const en = read("i18n/en.js"); // UI strings moved to the i18n catalog

test("the attention banners count only ENABLED rules, across all pages", () => {
  // Both banners (failing expression / waiting for data) query enabled rules
  // by eval_status, so a disabled rule's history isn't a current incident.
  // Every page of them (getAll), not the first 100 (Copilot hygiene #7).
  assert.match(rules, /getAll\("\/v1\/rules", \{ enabled: "true", eval_status: status \}\)/);
  assert.match(rules, /load\("error"\), load\("no_data"\)/);
});

test("a disabled rule's error renders as historical, not a current error badge", () => {
  // The disabled branch uses a NEUTRAL badge with the historical "off · last
  // error" label (now an i18n key)…
  assert.match(rules, /class="badge plain" title=\$\{t\("rules\.disabledLastErrorTitle"/);
  assert.match(rules, />\$\{t\("rules\.badgeOffLastError"\)\}<\/span>/);
  // …distinct from the enabled rule's current "error" WARNING badge, which is
  // only shown for a failing expression (a missing input is "no data").
  assert.match(rules, /if \(!r\.enabled\) \{/);
  assert.match(rules, /r\.eval_status === "error"\) return html`<span class="badge warning plain" title=\$\{r\.last_eval_error \|\| ""\}>\$\{t\("rules\.badgeError"\)\}</);
  // The historical wording itself lives in the catalog, unchanged.
  assert.match(en, /badgeOffLastError: "off · last error"/);
  assert.match(en, /disabledLastErrorTitle: "[^"]*historical/);
});

test("the dashboard scopes its 'with errors' count and link to enabled rules", () => {
  // Count query carries both has_error and enabled.
  assert.match(dashboard, /has_error:\s*"true",\s*enabled:\s*"true"/);
  // The drill-down link matches that scope.
  assert.match(dashboard, /#\/rules\?eval_status=error&enabled=true/);
});
