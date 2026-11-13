// V12: the log "why fired" drawer loads /v1/log/{id} for the selected row. If
// the user switches rows while a request is in flight and responses arrive out
// of order, the drawer must not adopt a stale response — it would show one
// notification while another is selected, and ack/snooze would act on the wrong
// one. The response is accepted only when it belongs to the current selection,
// and the actions bind to the selected row's identity.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { responseMatchesSelection } from "../../app/admin_ui/static/lib/select_guard.js";

test("out-of-order: a late response for a row navigated away from is rejected", () => {
  const A = { id: "n_A", type: "soc_low" };
  const B = { id: "n_B", type: "grid_up" };
  const respA = { id: "n_A", type: "soc_low", title: "A detail" };
  const respB = { id: "n_B", type: "grid_up", title: "B detail" };

  // Opened A then switched to B; B's response landed first, then A's. The
  // current selection is B: accept B's response, reject the late A response.
  assert.equal(responseMatchesSelection(B, respB), true);
  assert.equal(responseMatchesSelection(B, respA), false);
});

test("a response after the drawer closed (no selection) is rejected", () => {
  assert.equal(responseMatchesSelection(null, { id: "n_A" }), false);
  assert.equal(responseMatchesSelection(undefined, { id: "n_A" }), false);
});

test("the matching response for the current selection is accepted", () => {
  assert.equal(responseMatchesSelection({ id: "n_A" }, { id: "n_A", title: "x" }), true);
});

test("a malformed/empty response is rejected", () => {
  assert.equal(responseMatchesSelection({ id: "n_A" }, null), false);
  assert.equal(responseMatchesSelection({ id: "n_A" }, {}), false);
});

const logSrc = readFileSync(
  fileURLToPath(new URL("../../app/admin_ui/static/views/log.js", import.meta.url)),
  "utf8",
);

test("the drawer wires the guard, aborts in-flight loads, and binds actions to the selection", () => {
  // Response is gated through the guard, and the stale load is aborted.
  assert.match(logSrc, /responseMatchesSelection\(row, data\)/);
  assert.match(logSrc, /new AbortController\(\)/);
  assert.match(logSrc, /ctrl\.abort\(\)/);
  // ack + snooze target the selected row's identity, not the detail response.
  assert.match(logSrc, /\/v1\/log\/\$\{encodeURIComponent\(row\.id\)\}\/ack/);
  assert.match(logSrc, /target:\s*row\.type/);
  assert.match(logSrc, /from log \$\{row\.id\}/);
});
