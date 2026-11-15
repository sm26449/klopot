// UX-012: the Live Log starved under continuous traffic because each WS frame
// reset a 400ms debounce, so the timer never fired. makeCoalescer fires on a
// bounded cadence: once per window — not per frame, and not never.
import { test } from "node:test";
import assert from "node:assert/strict";
import { makeCoalescer } from "../../app/admin_ui/static/lib/coalesce.js";

test("a single trigger fires once after the wait", (t) => {
  t.mock.timers.enable(["setTimeout"]);
  let runs = 0;
  const c = makeCoalescer(() => { runs++; }, 400);
  c.trigger();
  t.mock.timers.tick(399);
  assert.equal(runs, 0, "not before the wait");
  t.mock.timers.tick(1);
  assert.equal(runs, 1, "fires at the wait");
  t.mock.timers.tick(5000);
  assert.equal(runs, 1, "no further fire without new triggers");
});

test("a continuous stream refreshes on a bounded cadence, not per frame", (t) => {
  t.mock.timers.enable(["setTimeout"]);
  let runs = 0;
  const c = makeCoalescer(() => { runs++; }, 400);
  // 10 triggers at 100ms spacing over ~1s — far faster than the 400ms window.
  for (let ms = 0; ms < 1000; ms += 100) { c.trigger(); t.mock.timers.tick(100); }
  // The old reset-on-each debounce would have produced 0 runs; a per-frame
  // reload would have produced 10. Coalesced: ~one per 400ms window.
  assert.ok(runs >= 2 && runs <= 3, `expected a bounded 2-3 runs, got ${runs}`);
});

test("cancel stops a pending fire", (t) => {
  t.mock.timers.enable(["setTimeout"]);
  let runs = 0;
  const c = makeCoalescer(() => { runs++; }, 400);
  c.trigger();
  c.cancel();
  t.mock.timers.tick(5000);
  assert.equal(runs, 0);
});
