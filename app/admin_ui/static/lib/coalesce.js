// Coalesced trailing trigger (audit UX-012).
//
// A plain debounce that calls clearTimeout on every signal never fires while
// signals keep arriving faster than the wait — the live firehose then starves
// the Log: continuous traffic resets the timer forever and the list never
// reloads. This instead fires `fn` at most once per `wait` ms, on the trailing
// edge of each window: the first signal schedules the run and later signals in
// that window only mark it dirty, they do NOT reset the timer. So a continuous
// stream produces a bounded, periodic refresh instead of none (or one per
// frame). Returns { trigger, cancel }.
export function makeCoalescer(fn, wait = 400) {
  let timer = null;
  let dirty = false;
  return {
    trigger() {
      dirty = true;
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        if (dirty) { dirty = false; fn(); }
      }, wait);
    },
    cancel() {
      if (timer) { clearTimeout(timer); timer = null; }
      dirty = false;
    },
  };
}

// No-overlap gate for a fire-and-forget reload whose completion is observed out
// of band — e.g. a `loading` flag (audit UX-012 / R4).
//
// The coalescer above caps the *rate* of reloads, but a loader that aborts its
// in-flight request on every reload still cancels work that never finishes when
// traffic is continuous and latency exceeds the window: many requests start,
// each superseded before it returns, zero complete. This gate serialises them:
// while a reload is in flight later invalidations only mark a refresh as due,
// and the next reload starts when the current one settles. Continuous traffic
// then yields periodic COMPLETED refreshes, not just periodic requests.
//
//   const f = makeSingleFlight();
//   onInvalidate: () => { if (f.request()) reload(); }   // start, or mark due
//   onSettled:    () => { if (f.settle())  reload(); }   // run the deferred one
export function makeSingleFlight() {
  let busy = false;
  let pending = false;
  return {
    // True if the caller should start a reload now; false if one is already in
    // flight (the refresh is remembered and run on settle()).
    request() {
      if (busy) { pending = true; return false; }
      busy = true;
      return true;
    },
    // Mark the in-flight reload done. True if a refresh came in meanwhile and
    // should start now (the gate stays busy for it); false if idle.
    settle() {
      busy = false;
      if (!pending) return false;
      pending = false;
      busy = true;
      return true;
    },
    get busy() { return busy; },
  };
}
