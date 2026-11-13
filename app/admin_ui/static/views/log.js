// Alerts log (phase F4): server-paginated table + filters + live tail +
// a "why fired" drawer with ack / snooze actions.
import { html, useState, useEffect, useCallback, useRef } from "../lib/h.js";
import { useLoader } from "../lib/loader.js";
import { useUrlFilters } from "../lib/router.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { openStream } from "../lib/ws.js";
import { makeCoalescer, makeSingleFlight } from "../lib/coalesce.js";
import { Drawer, Pager, Spinner, Empty, ErrorState, StaleBanner, Json, LiveStatus } from "../lib/ui.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import { responseMatchesSelection } from "../lib/select_guard.js";
import { t } from "../lib/i18n.js";

const LIMIT = 50;
const SEVERITIES = ["info", "warning", "critical"];

function isoInHours(h) {
  return new Date(Date.now() + h * 3600 * 1000).toISOString();
}

function SevBadge({ s }) {
  return html`<span class="badge ${s} plain sev">${s}</span>`;
}

// Settled delivery outcome (audit A03): sent / partial / failed /
// suppressed, from the persisted delivery_status with a defensive
// fallback for any pre-0009 row that lacks it.
function deliveryStatus(r) {
  if (r.delivery_status) return r.delivery_status;
  if (r.suppressed_reason) return "suppressed";
  const ok = (r.dispatched_to || []).length;
  const bad = Object.keys(r.failed_channels || {}).length;
  return ok ? (bad ? "partial" : "sent") : "failed";
}

function StatusBadge({ r }) {
  const s = deliveryStatus(r);
  if (s === "suppressed")
    return html`<span class="badge warning plain">${r.suppressed_reason || t("log.statusSuppressed")}</span>`;
  if (s === "failed") return html`<span class="badge down plain">${t("log.statusFailed")}</span>`;
  if (s === "partial") return html`<span class="badge warning plain">${t("log.statusPartial")}</span>`;
  // Still queued/retrying by the outbox worker — NOT delivered yet (F20).
  if (s === "pending") return html`<span class="badge warning plain">${t("log.statusPending")}</span>`;
  return r.acknowledged_at
    ? html`<span class="badge ok plain">${t("log.statusAcked")}</span>`
    : html`<span class="badge ok plain">${t("log.statusSent")}</span>`;
}

export function LogView({ query }) {
  // Filters AND the page offset live in the URL (UX-015/R5): they survive
  // reload/back/forward, deep-links and a rule's History link (?rule=<id>), and
  // any filter change resets to page 1. `status`/`ack`/`is_test`/`rule` map to
  // the API params in buildQuery below.
  const [filters, setFilter, resetFilters, offset, setOffset] = useUrlFilters("/log", query, {
    type: "", severity: "", status: "", ack: "", is_test: "", search: "", rule: "",
  });
  const [types, setTypes] = useState([]);
  const [selected, setSelected] = useState(null);
  const [live, setLive] = useState(false);
  const [wsStatus, setWsStatus] = useState(null); // real stream status (UX-013)
  const [newCount, setNewCount] = useState(0);
  const liveRef = useRef(null);

  // Template types for the "type" filter datalist (load once).
  useEffect(() => {
    api.get("/v1/templates", { limit: 500 })
      .then((p) => setTypes(p.items.map((t) => t.type).sort()))
      .catch(() => {});
  }, []);

  const buildQuery = useCallback(() => {
    const q = { skip: offset, limit: LIMIT };
    if (filters.type) q.type = filters.type;
    if (filters.severity) q.severity = filters.severity;
    if (filters.status === "dispatched") q.suppressed = "false";
    else if (["sent", "partial", "failed", "suppressed", "pending"].includes(filters.status))
      q.delivery_status = filters.status;
    if (filters.ack === "acked") q.acknowledged = "true";
    else if (filters.ack === "unacked") q.acknowledged = "false";
    if (filters.is_test) q.is_test = filters.is_test;
    if (filters.search) q.search = filters.search;
    if (filters.rule) q.rule_id = filters.rule;
    return q;
  }, [filters, offset]);

  // Debounced + cancelable load with a stale-response guard (audit A28).
  const [data, loading, reload, error] = useLoader(
    (signal) => api.get("/v1/log", buildQuery(), { signal }),
    [buildQuery],
  );
  // The "new since" counter belongs to the current view — reset it
  // whenever the filters/page change or we explicitly refresh.
  useEffect(() => { setNewCount(0); }, [buildQuery]);
  const load = useCallback(() => { setNewCount(0); reload(); }, [reload]);

  // UX-012 / R4: single-flight the live revalidation. The coalescer caps the
  // *rate* (one trigger per window) but useLoader aborts the in-flight request
  // on every reload — so continuous traffic with latency longer than the window
  // kept cancelling fetches that never completed. The gate never overlaps: while
  // a live reload is in flight, later invalidations only mark a refresh as due,
  // and the next one fires once the current settles — periodic COMPLETED
  // refreshes, not just periodic requests. Filter/offset changes still go
  // through useLoader's deps and abort independently (correctly discarding
  // now-stale results).
  const flight = useRef(null);
  if (flight.current === null) flight.current = makeSingleFlight();
  const liveReload = useCallback(() => {
    if (flight.current.request()) { setNewCount(0); reload(); }
  }, [reload]);
  // When a load settles, release the gate and start the deferred reload, if any.
  const prevLoading = useRef(loading);
  useEffect(() => {
    const was = prevLoading.current;
    prevLoading.current = loading;
    if (was && !loading && flight.current.settle()) { setNewCount(0); reload(); }
  }, [loading, reload]);

  const items = data?.items || [];
  const hasFilters = Object.values(filters).some(Boolean);

  // Refs so the long-lived WS callback sees current state without being
  // torn down on every filter/offset change.
  const liveState = useRef({});
  liveState.current = { load, liveReload, offset, hasFilters };

  // A21: a notification frame is an INVALIDATION signal, not a renderable
  // row — it lacks is_test/ack/suppressed and the real channel set, and
  // must respect the active filters/page. On a clean first page we reload
  // (canonical rows); otherwise we count them and let the operator refresh,
  // so filters and paging are never disturbed.
  useEffect(() => {
    if (!live) { setWsStatus(null); if (liveRef.current) { liveRef.current.close(); liveRef.current = null; } return undefined; }
    setNewCount(0);
    // UX-012: coalesce invalidations. A per-frame reset-on-each debounce starves
    // the list under continuous traffic (the timer is reset forever); this
    // reloads on a bounded ~400ms cadence instead, firing once per window.
    const reload = makeCoalescer(() => liveState.current.liveReload(), 400);
    const s = openStream("/v1/stream/notifications", {
      onStatus: setWsStatus,
      onMessage: (f) => {
        if (!f || f.type !== "notification" || !f.id) return;
        const st = liveState.current;
        if (st.offset === 0 && !st.hasFilters) reload.trigger();
        else setNewCount((n) => n + 1);
      },
    });
    liveRef.current = s;
    return () => { reload.cancel(); s.close(); liveRef.current = null; setWsStatus(null); };
  }, [live]);


  async function ack(row) {
    try { await api.post(`/v1/log/${encodeURIComponent(row.id)}/ack`); toast.ok(t("log.toastAcknowledged")); load(); }
    catch (e) { toast.error(e); }
  }

  return html`<div>
    <div class="page-head">
      <div><h1>${t("log.title")}</h1><p class="muted">${t("log.subtitle")}</p></div>
      <div class="actions">
        <label class="live-toggle" title=${t("log.liveTailTitle")}>
          <input type="checkbox" checked=${live} onChange=${(e) => setLive(e.target.checked)} />
          ${live ? html`<${LiveStatus} status=${wsStatus} />` : html`<span class="live-status"><span class="dot"></span> ${t("log.live")}</span>`}
        </label>
        <button class="btn sm" onClick=${load}>${t("log.refresh")}</button>
      </div>
    </div>

    <div class="card filters">
      <input list="log-types" aria-label=${t("log.filterByType")} placeholder=${t("log.typePlaceholder")} value=${filters.type} onInput=${(e) => setFilter("type", e.target.value)} />
      <datalist id="log-types">${types.map((t) => html`<option key=${t} value=${t}></option>`)}</datalist>
      <select aria-label=${t("log.filterBySeverity")} value=${filters.severity} onChange=${(e) => setFilter("severity", e.target.value)}>
        <option value="">${t("log.anySeverity")}</option>
        ${SEVERITIES.map((s) => html`<option key=${s} value=${s}>${s}</option>`)}
      </select>
      <select aria-label=${t("log.filterByStatus")} value=${filters.status} onChange=${(e) => setFilter("status", e.target.value)}>
        <option value="">${t("log.statusAll")}</option><option value="pending">${t("log.optPending")}</option><option value="sent">${t("log.optSent")}</option>
        <option value="partial">${t("log.optPartial")}</option><option value="failed">${t("log.optFailed")}</option><option value="suppressed">${t("log.optSuppressed")}</option>
      </select>
      <select aria-label=${t("log.filterByAck")} value=${filters.ack} onChange=${(e) => setFilter("ack", e.target.value)}>
        <option value="">${t("log.anyAck")}</option><option value="unacked">${t("log.optUnacked")}</option><option value="acked">${t("log.optAcked")}</option>
      </select>
      <select aria-label=${t("log.filterByTest")} value=${filters.is_test} onChange=${(e) => setFilter("is_test", e.target.value)}>
        <option value="">${t("log.realAndTest")}</option><option value="false">${t("log.realOnly")}</option><option value="true">${t("log.testOnly")}</option>
      </select>
      <input class="grow" aria-label=${t("log.searchLog")} placeholder=${t("log.searchPlaceholder")} value=${filters.search}
             onInput=${(e) => setFilter("search", e.target.value)} />
      ${hasFilters ? html`<button class="btn sm ghost" onClick=${resetFilters}>${t("log.clear")}</button>` : null}
    </div>

    ${live && newCount > 0 ? html`<button class="btn sm new-banner" onClick=${load}>
      ↑ ${t(newCount > 1 ? "log.newAlertsBanner" : "log.newAlertBanner", { n: newCount })}</button>` : null}

    ${error && data ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    <div class="card" style="margin-top:14px; padding:0">
      ${error && !data ? html`<${ErrorState} error=${error} onRetry=${reload} />` : loading && !data ? html`<${Spinner} />` : items.length === 0
        ? html`<${Empty} label=${t("log.emptyNoMatch")} />`
        : html`<table class="tbl log">
        <thead><tr>
          <th>${t("log.fired")}</th><th>${t("log.sev")}</th><th>${t("log.type")}</th><th>${t("log.titleCol")}</th><th>${t("log.dispatched")}</th><th>${t("log.status")}</th><th></th>
        </tr></thead>
        <tbody>${items.map((r) => html`<tr key=${r.id} style="cursor:pointer" onClick=${() => setSelected(r)}>
          <td class="nowrap"><button type="button" class="cell-btn" title=${fmtDateTime(r.fired_at)}
              aria-label=${t("log.rowAria", { title: r.title })} onClick=${(e) => { e.stopPropagation(); setSelected(r); }}>${fmtRelative(r.fired_at)}</button></td>
          <td><${SevBadge} s=${r.severity} /></td>
          <td class="mono small">${r.type}</td>
          <td>${r.title}</td>
          <td>${(r.dispatched_to || []).map((c) => html`<span key=${c} class="chip">${c}</span>`)}
            ${Object.keys(r.failed_channels || {}).length
              ? html`<span class="chip crit" title=${Object.entries(r.failed_channels).map(([k, v]) => `${k}: ${v}`).join("\n")}>✕ ${Object.keys(r.failed_channels).length}</span>` : null}</td>
          <td><${StatusBadge} r=${r} /></td>
          <td onClick=${(e) => e.stopPropagation()}>
            ${!r.acknowledged_at && !r.suppressed_reason
              ? html`<button class="btn sm" onClick=${() => ack(r)}>${t("log.ack")}</button>` : null}</td>
        </tr>`)}</tbody>
      </table>`}
      ${data ? html`<div style="padding:10px 14px"><${Pager} offset=${data.offset} limit=${data.limit} total=${data.total} onPage=${setOffset} /></div>` : null}
    </div>

    <${WhyFiredDrawer} row=${selected} onClose=${() => setSelected(null)} onChanged=${load} />
  </div>`;
}

// ── Why-fired drawer ───────────────────────────────────────────────
function WhyFiredDrawer({ row, onClose, onChanged }) {
  const [full, setFull] = useState(null);
  const [detailErr, setDetailErr] = useState(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    setFull(null); setDetailErr(null);
    if (!row) return undefined;
    // Abort the in-flight detail load and reject any late response when the
    // selection changes, so an out-of-order response can't replace the panel
    // for the row now selected or retarget its actions (audit V12).
    const ctrl = new AbortController();
    let active = true;
    api.get(`/v1/log/${encodeURIComponent(row.id)}`, null, { signal: ctrl.signal })
      .then((data) => { if (active && responseMatchesSelection(row, data)) setFull(data); })
      // A failed detail load used to be swallowed, leaving the list-row summary
      // looking complete; surface it with a retry (audit UX-006/R1).
      .catch((e) => { if (active && e && e.name !== "AbortError") setDetailErr(e); });
    return () => { active = false; ctrl.abort(); };
  }, [row, retry]);

  if (!row) return null;
  // `r` is for DISPLAY (richer when the detail has loaded); the guard above
  // guarantees `full` is always for the current row. Actions bind to `row` —
  // the selection identity — so they can never act on a stale response (V12).
  const r = full || row;

  async function ack() {
    try { await api.post(`/v1/log/${encodeURIComponent(row.id)}/ack`); toast.ok(t("log.toastAcknowledged")); onChanged?.(); onClose(); }
    catch (e) { toast.error(e); }
  }
  async function snoozeType(hours) {
    try {
      await api.post("/v1/snooze", { scope: "type", target: row.type, until: isoInHours(hours), reason: `from log ${row.id}` });
      toast.ok(t("log.toastSnoozed", { type: row.type, hours })); onChanged?.();
    } catch (e) { toast.error(e); }
  }

  return html`<${Drawer} open=${!!row} title=${r.title} onClose=${onClose}>
    <div class="why">
      ${detailErr ? html`<${StaleBanner} error=${detailErr} label=${t("common.detailError")}
        onRetry=${() => setRetry((n) => n + 1)} />` : null}
      <div class="why-row"><${SevBadge} s=${r.severity} />
        <span class="mono small">${r.type}</span>
        ${r.is_test ? html`<span class="badge plain">${t("log.testBadge")}</span>` : null}
        <${StatusBadge} r=${r} />
      </div>
      ${r.message ? html`<p class="why-msg">${r.message}</p>` : null}

      <dl class="kv">
        <dt>${t("log.fired")}</dt><dd title=${r.fired_at}>${fmtDateTime(r.fired_at)}</dd>
        <dt>${t("log.dispatchedTo")}</dt><dd>${(r.dispatched_to || []).length ? r.dispatched_to.map((c) => html`<span key=${c} class="chip">${c}</span>`) : "—"}</dd>
        ${Object.keys(r.failed_channels || {}).length ? html`<dt>${t("log.failedLabel")}</dt><dd>${Object.entries(r.failed_channels).map(([k, v]) => html`<div key=${k} class="small"><span class="chip crit">${k}</span> <span class="muted">${v}</span></div>`)}</dd>` : null}
        ${r.dispatch_latency_ms != null ? html`<dt>${t("log.latency")}</dt><dd>${r.dispatch_latency_ms} ms</dd>` : null}
        ${r.acknowledged_at ? html`<dt>${t("log.acked")}</dt><dd>${fmtDateTime(r.acknowledged_at)} ${r.acknowledged_by ? html`<span class="muted">${t("log.ackedBy", { by: r.acknowledged_by })}</span>` : null}</dd>` : null}
        ${r.escalated_at ? html`<dt>${t("log.escalated")}</dt><dd>${fmtDateTime(r.escalated_at)}</dd>` : null}
        ${r.rule_id ? html`<dt>${t("log.rule")}</dt><dd><a href=${`#/rules/${r.rule_id}`}>#${r.rule_id}</a></dd>` : null}
        ${r.source ? html`<dt>${t("log.source")}</dt><dd class="mono small">${r.source}</dd>` : null}
        ${r.trace_id ? html`<dt>${t("log.trace")}</dt><dd class="mono small">${r.trace_id}</dd>` : null}
      </dl>

      ${r.vars_payload ? html`<h3 class="why-h">${t("log.variables")}</h3><${Json} value=${r.vars_payload} />` : null}

      <div class="why-actions">
        ${!r.acknowledged_at && !r.suppressed_reason ? html`<button class="btn primary sm" onClick=${ack}>${t("log.acknowledge")}</button>` : null}
        <span class="muted small">${t("log.snoozeType")}</span>
        <button class="btn sm" onClick=${() => snoozeType(1)}>1h</button>
        <button class="btn sm" onClick=${() => snoozeType(8)}>8h</button>
        <button class="btn sm" onClick=${() => snoozeType(24)}>24h</button>
      </div>
    </div>
  </${Drawer}>`;
}
