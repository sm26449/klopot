// UX-012 / R4: the Live Log coalescer caps the *rate* of reloads, but useLoader
// aborts its in-flight request on every reload. Under continuous traffic with
// latency longer than the coalescing window, each reload cancelled a fetch that
// never completed — periodic requests, zero completions. makeSingleFlight
// serialises reloads so one always runs to completion before the next starts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { makeCoalescer, makeSingleFlight } from "../../app/admin_ui/static/lib/coalesce.js";

test("request() starts one reload and defers the rest while busy", () => {
  const f = makeSingleFlight();
  assert.equal(f.request(), true, "first request starts immediately");
  assert.equal(f.busy, true);
  assert.equal(f.request(), false, "a second request while busy is deferred");
  assert.equal(f.request(), false, "further requests collapse into the one pending");
});

test("settle() runs exactly one deferred reload, then goes idle", () => {
  const f = makeSingleFlight();
  f.request();                 // in flight
  f.request();                 // one deferred
  assert.equal(f.settle(), true, "a deferred reload starts on settle");
  assert.equal(f.busy, true, "the gate stays busy for it");
  assert.equal(f.settle(), false, "nothing deferred now — idle");
  assert.equal(f.busy, false);
});

test("settle() with nothing pending just releases the gate", () => {
  const f = makeSingleFlight();
  f.request();
  assert.equal(f.settle(), false);
  assert.equal(f.busy, false);
  assert.equal(f.request(), true, "the next request starts fresh");
});

// The regression itself: coalescer + single-flight + a fetch slower than the
// window, driven by continuous frames. The pre-R4 code (coalescer calling an
// aborting reload) completed ZERO; the gate must complete periodically.
test("continuous traffic with latency > window yields periodic COMPLETIONS", (t) => {
  t.mock.timers.enable(["setTimeout"]);
  const LATENCY = 900;   // GET /v1/log round-trip
  const WINDOW = 400;    // coalescing window
  let started = 0;
  let completed = 0;
  let aborted = 0;
  const flight = makeSingleFlight();

  // A reload: if the gate lets us start, kick off a LATENCY-ms fetch. On
  // completion, settle the gate and start the deferred reload, if any.
  const doReload = () => {
    if (!flight.request()) return;
    startFetch();
  };
  function startFetch() {
    started++;
    const token = started;
    setTimeout(() => {
      // Not superseded (single-flight guarantees this) — it completes.
      completed++;
      if (flight.settle()) startFetch();   // run the deferred one
      void token;
    }, LATENCY);
  }
  // Also assert the OLD behaviour would have aborted: a naive reload that
  // cancels the previous in-flight on each call.
  let naiveInFlight = null;
  const naiveReload = () => {
    if (naiveInFlight !== null) { aborted++; naiveInFlight = null; } // abort prev
    const token = Symbol();
    naiveInFlight = token;
    setTimeout(() => { if (naiveInFlight === token) naiveInFlight = null; }, LATENCY);
  };

  const coalescer = makeCoalescer(() => doReload(), WINDOW);
  const naiveCoalescer = makeCoalescer(() => naiveReload(), WINDOW);

  // ~5s of frames at 10/s (every 100ms) — far faster than the 900ms fetch.
  for (let ms = 0; ms < 5000; ms += 100) {
    coalescer.trigger();
    naiveCoalescer.trigger();
    t.mock.timers.tick(100);
  }
  t.mock.timers.tick(LATENCY + WINDOW); // let the last in-flight settle

  assert.ok(completed >= 3, `single-flight completed periodically, got ${completed}`);
  // With a ~900ms fetch over ~5.9s, completions are paced by latency, not frames.
  assert.ok(completed <= 8, `completions are latency-paced, not per-frame, got ${completed}`);
  assert.ok(aborted >= 3, `the naive reload would have aborted repeatedly, got ${aborted}`);
});
