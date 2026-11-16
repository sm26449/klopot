// Accessible dialog behaviour shared by Drawer + Modal (audit A25).
//
// Provides, for any open dialog element:
//   - initial focus moved into the dialog;
//   - a focus trap so Tab/Shift+Tab cycle within it;
//   - focus return to the previously focused element on close;
//   - a dialog STACK so Escape only closes the top-most dialog (opening a
//     confirm Modal over a Drawer and pressing Escape must close one, not
//     both — the audit saw 2→0).
import { useEffect, useRef } from "./h.js";

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),' +
  'select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

const _stack = [];
let _bound = false;

function _bindGlobalEscape() {
  if (_bound) return;
  _bound = true;
  // Capture phase so we see Escape before any per-field handler; only the
  // top-of-stack dialog consumes it.
  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || _stack.length === 0) return;
    e.preventDefault();
    e.stopPropagation();
    _stack[_stack.length - 1].onClose?.();
  }, true);
}

/** Whether a dialog (drawer, modal, the search palette) is open. It owns
 *  focus: nothing outside it — a route change — may take focus away. */
export function dialogOpen() {
  return _stack.length > 0;
}

let _seq = 0;
export function dialogTitleId(prefix = "dlg") {
  // Stable enough per render; only needs to be unique among mounted dialogs.
  _seq = (_seq + 1) % 1e6;
  return `${prefix}-title-${_seq}`;
}

export function useDialog(open, onClose, elRef) {
  // Keep the LATEST onClose in a ref, refreshed every render, and have the
  // stack call through it. The effect only re-runs on `open`, so the focus
  // trap isn't remounted each render — but Escape still invokes the current
  // onClose. Without this, a dialog whose onClose starts undefined and becomes
  // a real callback later (e.g. the "copy this key" modal, enabled only after
  // "I have saved…" is ticked) kept the stale undefined and Escape did nothing
  // (audit V18).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    if (!open) return undefined;
    _bindGlobalEscape();
    const entry = { onClose: () => onCloseRef.current?.() };
    _stack.push(entry);

    const el = elRef.current;
    const prevFocus = document.activeElement;
    const focusables = () => (el ? Array.from(el.querySelectorAll(FOCUSABLE)) : []);

    // Move focus into the dialog (first control, else the container).
    (focusables()[0] || el)?.focus?.();

    const onKey = (e) => {
      if (e.key !== "Tab") return;
      const f = focusables();
      if (f.length === 0) { e.preventDefault(); el?.focus?.(); return; }
      const first = f[0];
      const last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    el?.addEventListener("keydown", onKey);

    return () => {
      el?.removeEventListener("keydown", onKey);
      const i = _stack.indexOf(entry);
      if (i >= 0) _stack.splice(i, 1);
      // Restore focus to whatever opened the dialog.
      if (prevFocus && typeof prevFocus.focus === "function") prevFocus.focus();
    };
    // eslint-disable-next-line
  }, [open]);
}
