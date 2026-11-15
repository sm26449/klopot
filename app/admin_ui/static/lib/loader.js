// Debounced, cancelable list loader (audit A28 + UX-006).
//
// The data views reloaded on every keystroke, wrote the response straight
// into state, and had no way to cancel an in-flight request — so a slow
// earlier response could clobber a newer one, and a *failed* request left a
// permanent spinner or a false "empty". useLoader fixes all of that:
//
//   - debounces filter-change fetches (default 300 ms) so typing doesn't spam
//     the API, but runs the FIRST load and any explicit reload() immediately;
//   - aborts the previous request via AbortController;
//   - guards with a generation counter so only the latest result is applied;
//   - exposes an explicit `error` (and clears it on the next attempt) so views
//     can show a persistent error + retry instead of a stuck spinner.
//
// Usage:
//   const [data, loading, reload, error] = useLoader(
//     (signal) => api.get("/v1/rules", q, { signal }),
//     [filters, offset],
//   );
//   render: error && !data ? <ErrorState onRetry=reload/>
//         : data === null  ? <Spinner/>
//         : data.items.length === 0 ? <Empty/> : <table/>
import { useState, useEffect, useRef, useCallback } from "./h.js";

export function useLoader(fetcher, deps, { debounceMs = 300, onError } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);   // an initial fetch is pending
  const [error, setError] = useState(null);
  const gen = useRef(0);
  const immediate = useRef(true);                  // first load + reload() are not debounced
  const [nonce, setNonce] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // Imperative refresh (after a save/delete, or a retry) — immediate, and part
  // of the effect deps via the nonce.
  const reload = useCallback(() => { immediate.current = true; setNonce((n) => n + 1); }, []);

  useEffect(() => {
    const myGen = ++gen.current;
    const ac = new AbortController();
    const wait = immediate.current ? 0 : debounceMs;
    immediate.current = false;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const result = await fetcherRef.current(ac.signal);
        if (myGen === gen.current) { setData(result); setError(null); }
      } catch (e) {
        if (e && e.name === "AbortError") return;        // superseded — ignore
        if (myGen === gen.current) { setError(e); if (onError) onError(e); }
      } finally {
        if (myGen === gen.current) setLoading(false);
      }
    }, wait);
    return () => { clearTimeout(timer); ac.abort(); };
    // eslint-disable-next-line
  }, [...deps, nonce]);

  return [data, loading, reload, error];
}
