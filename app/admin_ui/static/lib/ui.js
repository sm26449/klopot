// Shared UI primitives for the data views (F4+).
import { html, useEffect, useRef, useState } from "./h.js";
import { useDialog, dialogTitleId } from "./dialog.js";
import { addNavGuard } from "./router.js";
import { t } from "./i18n.js";

// Live-stream connection indicator (audit UX-013). Per ADR-0001 stream health
// uses the severity colours + a text label, never the amber "live" dot, so a
// dropped stream reads as reconnecting/disconnected instead of a stale
// "connected". Maps the WS status (from lib/ws.js openStream onStatus) to a dot
// severity class and a localized label; announces changes politely.
const LIVE_STATUS = {
  open: { cls: "ok", key: "common.wsLive" },
  connecting: { cls: "warn", key: "common.wsConnecting" },
  reconnecting: { cls: "warn", key: "common.wsReconnecting" },
  "auth-ended": { cls: "crit", key: "common.wsAuthEnded" },
  closed: { cls: "", key: "common.wsConnecting" },
};
export function LiveStatus({ status }) {
  const s = LIVE_STATUS[status] || LIVE_STATUS.connecting;
  return html`<span class="live-status">
    <span class=${"dot " + s.cls}></span>
    <span aria-live="polite">${t(s.key)}</span>
  </span>`;
}

// ── Drawer ─────────────────────────────────────────────────────────
// Right-side slide-over. `open` controls visibility; `onClose` fires on
// overlay click / Esc / the close button. Accessible dialog semantics
// (initial focus, focus trap, focus return, top-only Escape) via
// useDialog (audit A25).
// Track whether a form has unsaved changes: compare the current values to a
// snapshot of the first render (audit UX-007). Pass a plain object of the form
// state; returns true once it differs from how it opened.
export function useDirty(current) {
  const initial = useRef(undefined);
  const now = JSON.stringify(current);
  if (initial.current === undefined) initial.current = now;
  return now !== initial.current;
}

// Warn before leaving the tab/reloading while there are unsaved changes.
function useBeforeUnload(active) {
  useEffect(() => {
    if (!active) return undefined;
    const h = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [active]);
}

export function Drawer({ open, title, onClose, children, width = 520, dirty = false }) {
  const ref = useRef(null);
  const titleId = dialogTitleId("drawer");
  // All close paths (Escape via useDialog, overlay click, X) go through this, so
  // a dirty editor confirms once before discarding — Esc/overlay/X and tab-close
  // are all guarded (audit UX-007).
  const requestClose = () => {
    if (dirty && typeof window.confirm === "function" && !window.confirm(t("common.discardChanges"))) return;
    onClose();
  };
  useDialog(open, requestClose, ref);
  useBeforeUnload(open && dirty);
  // Guard in-app navigation while dirty (sidebar link, back/forward, hash) — the
  // beforeunload above only covers a real tab close/reload (audit UX-007/R2).
  useEffect(() => {
    if (!(open && dirty)) return undefined;
    return addNavGuard(() => typeof window.confirm !== "function" || window.confirm(t("common.discardChanges")));
  }, [open, dirty]);
  if (!open) return null;
  return html`<div class="drawer-overlay" onClick=${requestClose}>
    <aside ref=${ref} class="drawer" style=${`width:min(${width}px, 94vw)`} tabindex="-1"
           onClick=${(e) => e.stopPropagation()}
           role="dialog" aria-modal="true" aria-labelledby=${titleId}>
      <header class="drawer-head">
        <h2 id=${titleId}>${title || t("common.details")}</h2>
        <button class="btn sm ghost" onClick=${requestClose} aria-label=${t("common.close")}>✕</button>
      </header>
      <div class="drawer-body">${children}</div>
    </aside>
  </div>`;
}

// ── Pager ──────────────────────────────────────────────────────────
// Server-side pagination controls. offset/limit/total in; onPage(newOffset).
export function Pager({ offset, limit, total, onPage }) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  const canPrev = offset > 0;
  const canNext = offset + limit < total;
  return html`<div class="pager">
    <span class="muted small">${t("common.pageRange", { from, to, total })}</span>
    <span class="spacer"></span>
    <button class="btn sm" disabled=${!canPrev} onClick=${() => onPage(Math.max(0, offset - limit))}>${t("common.prev")}</button>
    <button class="btn sm" disabled=${!canNext} onClick=${() => onPage(offset + limit)}>${t("common.next")}</button>
  </div>`;
}

// Visible item count + truncation notice for list views (audit A30):
// the views fetch a single capped page and ignored `total`, so a list
// longer than the cap was silently truncated with no indication.
export function ListMeta({ total, limit }) {
  if (total == null) return null;
  const truncated = limit != null && total > limit;
  return html`<div class=${"list-meta muted small" + (truncated ? " warn" : "")} role="status">
    ${truncated
      ? html`${t("common.showingFirst", { limit, total })}`
      : html`${t("common.itemCount", { count: total })}`}
  </div>`;
}

// ── KindHelp ───────────────────────────────────────────────────────
// Tiered, per-kind guidance shown at the bottom of an editor: one always-
// visible lead line + an expandable "Details" with purpose, the fields to
// fill, an example and tips. `help` is a structured i18n node (see tnode):
//   { lead, purpose?, fields?: [{name, desc}], example?, tips?: [string] }
// Any missing section is simply skipped; with only a lead, no disclosure is
// rendered. Content is data from the catalog, so it translates with the UI.
export function KindHelp({ help }) {
  if (!help || !help.lead) return null;
  const hasMore = help.purpose || help.fields?.length || help.example || help.tips?.length;
  return html`<aside class="kind-help" aria-label=${t("common.help")}>
    <p class="kind-help-lead"><span class="kind-help-icon" aria-hidden="true">💡</span> ${help.lead}</p>
    ${hasMore ? html`<details class="kind-help-details">
      <summary>${t("common.details")}</summary>
      ${help.purpose ? html`<p>${help.purpose}</p>` : null}
      ${help.fields?.length ? html`<dl class="kind-help-fields">
        ${help.fields.map((f) => html`<div key=${f.name}><dt>${f.name}</dt><dd>${f.desc}</dd></div>`)}
      </dl>` : null}
      ${help.example ? html`<p class="kind-help-example"><b>${t("common.example")}</b> <code>${help.example}</code></p>` : null}
      ${help.tips?.length ? html`<ul class="kind-help-tips">${help.tips.map((tip, i) => html`<li key=${i}>${tip}</li>`)}</ul>` : null}
    </details>` : null}
  </aside>`;
}

// ── Small helpers ──────────────────────────────────────────────────
export function Spinner({ label = t("common.loading") }) {
  return html`<p class="muted" style="padding:12px 0">${label}</p>`;
}

export function Empty({ label = t("common.nothingHere") }) {
  return html`<p class="muted" style="padding:18px 0; text-align:center">${label}</p>`;
}

// Persistent load-error with a retry (audit UX-006). Replaces the stuck spinner
// / false "empty" a failed fetch used to leave. `onRetry` re-runs the loader.
export function ErrorState({ error, onRetry, label }) {
  return html`<div class="error-state" role="alert">
    <p class="error-state-msg">${label || t("common.loadError")}</p>
    ${error && error.message ? html`<p class="muted small">${error.message}</p>` : null}
    ${onRetry ? html`<button class="btn sm" onClick=${onRetry}>${t("common.retry")}</button>` : null}
  </div>`;
}

// Persistent "refresh failed" strip shown ABOVE data that is already on screen
// (audit UX-006 / R1). A failed FIRST load uses ErrorState — it replaces the
// empty view. A failed REFRESH must keep the last-good data visible but say so,
// with a retry; otherwise stale rows silently look current. Views render this
// when `error && data` and keep ErrorState for `error && !data`.
export function StaleBanner({ error, onRetry, label }) {
  return html`<div class="stale-banner" role="alert">
    <span class="stale-banner-msg">${label || t("common.refreshFailed")}</span>
    ${error && error.message ? html`<span class="muted small">${error.message}</span>` : null}
    ${onRetry ? html`<button class="btn sm" onClick=${onRetry}>${t("common.retry")}</button>` : null}
  </div>`;
}

// Unsaved-draft recovery strip shown at the top of an editor (audit UX-007).
// A session that expires mid-edit unmounts the whole shell, so the dirty-close
// guards can't fire; the useDraft hook in lib/draft.js persists the draft to
// sessionStorage instead. On reopen, this offers to restore it or discard it.
export function DraftBanner({ onRestore, onDiscard }) {
  return html`<div class="draft-banner" role="status">
    <span class="draft-banner-msg">${t("common.draftFound")}</span>
    <span class="spacer"></span>
    <button class="btn sm" onClick=${onRestore}>${t("common.draftRestore")}</button>
    <button class="btn sm ghost" onClick=${onDiscard}>${t("common.draftDiscard")}</button>
  </div>`;
}

// JSON pretty block (read-only), used by the why-fired drawer.
export function Json({ value }) {
  let text;
  try { text = JSON.stringify(value, null, 2); } catch { text = String(value); }
  return html`<pre class="json">${text}</pre>`;
}

// ── Modal ──────────────────────────────────────────────────────────
export function Modal({ open, title, onClose, children, width = 440 }) {
  const ref = useRef(null);
  const titleId = dialogTitleId("modal");
  useDialog(open, onClose, ref);
  if (!open) return null;
  return html`<div class="modal-overlay" onClick=${onClose}>
    <div ref=${ref} class="modal" style=${`width:min(${width}px, 94vw)`} tabindex="-1"
         onClick=${(e) => e.stopPropagation()} role="dialog" aria-modal="true"
         aria-labelledby=${title ? titleId : undefined} aria-label=${title ? undefined : t("common.dialog")}>
      ${title ? html`<h2 id=${titleId}>${title}</h2>` : null}
      ${children}
    </div>
  </div>`;
}

// Lightweight confirmation for a recoverable action (no typed token): states
// what will happen, runs `onConfirm` only on the primary button, and cancelling
// does nothing (audit UX-016/R6). Use for restart/reset, not for deletes.
export function ConfirmModal({ open, title, message, confirmLabel, cancelLabel, onConfirm, onClose, busy, danger }) {
  return html`<${Modal} open=${open} title=${title} onClose=${onClose}>
    ${message ? html`<p>${message}</p>` : null}
    <div class="form-actions" style="margin-top:14px; justify-content:flex-end">
      <button class="btn" onClick=${onClose} disabled=${busy}>${cancelLabel || t("common.cancel")}</button>
      <button class=${"btn " + (danger ? "danger" : "primary")} onClick=${onConfirm} disabled=${busy}>${confirmLabel || t("common.confirm")}</button>
    </div>
  </${Modal}>`;
}

// Destructive confirmation that requires typing an exact token (name).
// `warning` is an optional extra line (e.g. "N rules reference this").
export function DangerConfirm({ open, token, title, warning, confirmLabel = t("common.delete"), onConfirm, onClose, busy }) {
  const [typed, setTyped] = useState("");
  useEffect(() => { if (open) setTyped(""); }, [open]);
  const ok = typed === token;
  return html`<${Modal} open=${open} title=${title} onClose=${onClose}>
    ${warning ? html`<div class="alert warn">${warning}</div>` : null}
    <p>${(() => { const p = t("common.typeToConfirm").split("{token}"); return html`${p[0]}<code>${token}</code>${p[1] ?? ""}`; })()}</p>
    <input autofocus value=${typed} onInput=${(e) => setTyped(e.target.value)} placeholder=${token} />
    <div class="form-actions" style="margin-top:14px; justify-content:flex-end">
      <button class="btn" onClick=${onClose} disabled=${busy}>${t("common.cancel")}</button>
      <button class="btn danger" disabled=${!ok || busy} onClick=${onConfirm}>${confirmLabel}</button>
    </div>
  </${Modal}>`;
}
