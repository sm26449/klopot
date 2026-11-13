// Guarded one-at-a-time async action (audit UX-016).
//
// Side-effecting buttons (channel test, breaker reset, input restart, schedule
// test) left themselves enabled while the request was in flight, so a fast
// double-click fired the effect twice. useGuard() runs an action at most once at
// a time: a synchronous ref blocks a second activation before the first
// resolves (and before the disabled state has re-rendered), and `busy` disables
// the control. A second call while busy is a no-op and returns undefined.
import { useState, useRef, useCallback } from "./h.js";

export function useGuard() {
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const run = useCallback(async (fn) => {
    if (running.current) return undefined;
    running.current = true;
    setBusy(true);
    try {
      return await fn();
    } finally {
      running.current = false;
      setBusy(false);
    }
  }, []);
  return [busy, run];
}
