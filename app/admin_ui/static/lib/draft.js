// Unsaved-draft recovery (audit UX-007).
//
// The dirty-close guards in lib/ui.js (Drawer confirm, beforeunload, nav guard)
// cover the paths where the editor stays mounted. They can't help when the
// SESSION expires mid-edit: a 401 fires `auth:expired`, which unmounts the whole
// shell straight to <Login>, so an open editor's draft is gone with no prompt.
//
// This module persists a dirty draft to sessionStorage keyed by editor + id, so
// the work survives the expiry → re-login round-trip (same tab, no reload). On
// reopen, the editor shows a DraftBanner offering restore or discard. We use
// sessionStorage, not localStorage, on purpose: a draft is a short-lived
// per-tab convenience, so it clears when the tab closes instead of lingering as
// a stale offer forever. Every access is guarded — storage can be absent or
// throw in private mode — and the editor works unchanged when it is.

import { useMemo, useRef, useState, useEffect } from "./h.js";

const PREFIX = "alertd.draft.";

export function draftKey(view, id) {
  return `${PREFIX}${view}.${id == null ? "new" : id}`;
}

function read(key) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw == null ? null : JSON.parse(raw);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* no storage / quota / private mode — draft recovery is best-effort */
  }
}

function remove(key) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

// Persist `value` to sessionStorage whenever `dirty`, keyed by (view, id). Reads
// any pre-existing draft ONCE at mount into `recovered` (null when none). The
// caller renders a DraftBanner while `recovered` is non-null, wires its buttons
// to `restore`/`dismiss`, and calls `clear()` on a successful save or a
// deliberate close so the stored draft can't resurface.
//
// Two independent flags, because "the recovery banner is handled" and "stop
// persisting" are different events:
//   • `handled`  hides the banner (restore OR dismiss). Persistence continues,
//                so edits made AFTER a restore are themselves recoverable.
//   • `stopped`  turns persistence off and keeps the slot empty (clear). Set on
//                save/close, when there is nothing left worth recovering. It
//                must win over `dirty`, or the save-time re-render would rewrite
//                the draft we just removed.
//
// Returns:
//   recovered  the parsed draft found at mount, or null once handled
//   restore()  hides the banner; the caller applies `recovered` to its setters
//   dismiss()  drops the stored draft and hides the banner (keeps persisting)
//   clear()    drops the stored draft and stops persisting (use on save/close)
export function useDraft(view, id, value, dirty) {
  const key = useMemo(() => draftKey(view, id), [view, id]);
  // Snapshot the stored draft exactly once, before our own persistence can
  // overwrite it — otherwise the first dirty render would clobber it with the
  // current (un-restored) form state.
  const recoveredRef = useRef(undefined);
  if (recoveredRef.current === undefined) recoveredRef.current = read(key);
  const [handled, setHandled] = useState(false);
  const [stopped, setStopped] = useState(false);

  useEffect(() => {
    if (stopped) { remove(key); return; }
    if (dirty) write(key, value);
  }, [key, dirty, value, stopped]);

  return {
    recovered: handled ? null : recoveredRef.current,
    restore: () => setHandled(true),
    dismiss: () => { setHandled(true); remove(key); },
    clear: () => { setStopped(true); remove(key); },
  };
}
