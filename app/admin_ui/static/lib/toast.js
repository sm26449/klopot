// Tiny toast bus. `toast.ok("Saved")`, `toast.error(err)` (ApiError aware).
import { html, useEffect, useState } from "./h.js";
import { t } from "./i18n.js";

const subs = new Set();
let seq = 0;

// A localized, contextual lead for common failures, so a 403/409/429/5xx/network
// error reads as what the user can do about it instead of a raw server string
// (audit UX-018).
function errorText(e) {
  const s = e.status;
  let hint = null;
  if (s === 403) hint = "common.errForbidden";
  else if (s === 409 || s === 412) hint = "common.errConflict";
  else if (s === 429) hint = "common.errRateLimited";
  else if (!s || e.code === "NETWORK" || e.code === "NETWORK_ERROR") hint = "common.errNetwork";
  else if (s >= 500) hint = "common.errServer";
  const base = e.message || t("common.errUnexpected");
  return hint ? `${t(hint)} ${base}` : base;
}

function push(kind, text, mono) {
  const item = { id: ++seq, kind, text, mono };
  for (const fn of subs) fn(item);
}

export const toast = {
  ok: (text) => push("ok", text),
  info: (text) => push("info", text),
  error(errOrText) {
    if (typeof errOrText === "string") return push("error", errOrText);
    const e = errOrText || {};
    const mono = e.traceId ? `trace ${e.traceId}` : (e.code ? e.code : null);
    push("error", errorText(e), mono);
  },
};

export function Toasts() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    const fn = (item) => {
      setItems((cur) => [...cur, item]);
      setTimeout(() => setItems((cur) => cur.filter((i) => i.id !== item.id)), item.kind === "error" ? 9000 : 4000);
    };
    subs.add(fn);
    return () => subs.delete(fn);
  }, []);
  return html`<div class="toasts" role="status" aria-live="polite">
    ${items.map((i) => html`<div key=${i.id} class="toast ${i.kind}">
      ${i.text}${i.mono ? html`<span class="mono">${i.mono}</span>` : null}
    </div>`)}
  </div>`;
}
