// Minimal hash router: "#/rules/42?tab=x" → { path: "/rules/42", params: {id:"42"}, query: {...} }.
import { useEffect, useState, useRef } from "./h.js";

function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [pathPart, queryPart = ""] = raw.split("?");
  const path = pathPart.startsWith("/") ? pathPart : "/" + pathPart;
  const query = Object.fromEntries(new URLSearchParams(queryPart));
  return { path, query };
}

// ── Navigation guard (audit UX-007 / R2) ───────────────────────────
// beforeunload only covers a real tab close/reload, not SPA hash routing. A
// dirty editor registers a guard; an in-app navigation (sidebar link,
// back/forward, programmatic navigate) that no guard approves is reverted, so
// the draft survives. A guard returns true when it's OK to leave (it may ask).
const _navGuards = new Set();
let _navApproved = false;   // a navigate() we already approved — don't re-ask on its hashchange
let _lastHash = null;
let _reverting = false;

function _okToLeave() { for (const g of _navGuards) { if (!g()) return false; } return true; }

// A dirty editor registers a guard (returns true when it's OK to leave, may
// confirm). The veto is enforced INSIDE useRoute so the view never switches on
// a declined navigation — reverting after the route changed would transiently
// unmount the editor and lose the draft.
export function addNavGuard(fn) { _navGuards.add(fn); return () => _navGuards.delete(fn); }

export function navigate(path, query, { replace = false, force = false } = {}) {
  const qs = query && Object.keys(query).length ? "?" + new URLSearchParams(query).toString() : "";
  const url = "#" + path + qs;
  if (!force && !_okToLeave()) return;   // a guard blocked it (user declined)
  _navApproved = true;
  // `replace` keeps typing in a filter from spamming the history stack (UX-015);
  // dispatch hashchange so useRoute still re-resolves the (replaced) URL.
  if (replace && window.history && window.history.replaceState) {
    window.history.replaceState(null, "", url);
    window.dispatchEvent(new Event("hashchange"));
  } else {
    window.location.hash = url;
  }
}

export function matchRoute(pattern, path) {
  const pp = pattern.split("/").filter(Boolean);
  const sp = path.split("/").filter(Boolean);
  if (pp.length !== sp.length) return null;
  const params = {};
  for (let i = 0; i < pp.length; i++) {
    if (pp[i].startsWith(":")) params[pp[i].slice(1)] = decodeURIComponent(sp[i]);
    else if (pp[i] !== sp[i]) return null;
  }
  return params;
}

export function useRoute() {
  const [route, setRoute] = useState(parseHash);
  useEffect(() => {
    if (_lastHash == null) _lastHash = window.location.hash;
    const onChange = () => {
      // After our own revert, just re-sync to the (restored) hash.
      if (_reverting) { _reverting = false; _lastHash = window.location.hash; setRoute(parseHash()); return; }
      // A dirty editor can veto this navigation (UX-007/R2): revert the hash and
      // do NOT switch the view, so the component — and its draft — stay mounted.
      if (!_navApproved && _navGuards.size > 0 && !_okToLeave()) {
        _reverting = true;
        window.location.hash = _lastHash || "";
        return;
      }
      _navApproved = false;
      _lastHash = window.location.hash;
      setRoute(parseHash());
    };
    window.addEventListener("hashchange", onChange);
    // The hash may have changed between the initial render and this
    // subscription (e.g. a redirect issued by a parent) — re-sync.
    onChange();
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

// Keeps a filter object AND the page offset in sync with the URL hash query
// (UX-015 / R5): initial values come from the URL, changes are written back, and
// it resyncs on back/forward/deep-link/external query. Only non-default values
// go in the URL; the page offset rides a reserved `skip` key. One contract for
// every paged list, so pagination survives reload and any filter change — from
// the UI *or* from the URL — resets to the first page (a stale `skip=50` can no
// longer leak onto a freshly filtered query). Returns
// [filters, setFilter, resetFilters, offset, setOffset].
export function useUrlFilters(basePath, query, defaults) {
  const keys = Object.keys(defaults);
  const fromUrl = () => {
    const f = {};
    for (const k of keys) f[k] = query && query[k] != null ? query[k] : defaults[k];
    return f;
  };
  const readSkip = () => {
    const n = parseInt(query && query.skip, 10);
    return Number.isFinite(n) && n > 0 ? n : 0;
  };
  const [filters, setFilters] = useState(fromUrl);
  const [offset, setOffsetState] = useState(readSkip);
  // The signature spans the filter keys AND skip, so a changed URL resyncs both.
  // `skip` falling back to 0 when absent means an external query like
  // `?enabled=true` lands on page 1, never on the old offset.
  const urlSig = keys.map((k) => (query && query[k] != null ? query[k] : "")).join("\u0001")
    + "\u0001skip=" + readSkip();
  // Resync ONLY when the URL actually changes between renders (back / forward /
  // deep-link). Comparing to the previous signature (not to our own writes)
  // means the deferred mount effect never reverts a local change.
  const prevUrlSig = useRef(urlSig);
  useEffect(() => {
    if (prevUrlSig.current === urlSig) return;
    prevUrlSig.current = urlSig;
    setFilters(fromUrl());
    setOffsetState(readSkip());
  }, [urlSig]); // eslint-disable-line

  function writeUrl(nextFilters, nextOffset, replace) {
    const q = {};
    for (const k of keys) if (nextFilters[k] && nextFilters[k] !== defaults[k]) q[k] = nextFilters[k];
    if (nextOffset > 0) q.skip = String(nextOffset);
    navigate(basePath, q, { replace });
  }
  // A filter change resets to the first page; filter writes `replace` so typing
  // doesn't spam history.
  function setFilter(k, v) { const n = { ...filters, [k]: v }; setFilters(n); setOffsetState(0); writeUrl(n, 0, true); }
  function resetFilters() { const n = { ...defaults }; setFilters(n); setOffsetState(0); writeUrl(n, 0, true); }
  // Page changes push a history entry so browser back/forward moves pages.
  function setOffset(n) { const off = Math.max(0, n | 0); setOffsetState(off); writeUrl(filters, off, false); }
  return [filters, setFilter, resetFilters, offset, setOffset];
}

export function resolve(routes, path) {
  for (const r of routes) {
    const params = matchRoute(r.path, path);
    if (params) return { ...r, params };
  }
  return null;
}
