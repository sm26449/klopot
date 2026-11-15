import { html, useState, useEffect } from "../lib/h.js";
import { api } from "../lib/api.js";
import { useLoader } from "../lib/loader.js";
import { useUrlFilters, navigate } from "../lib/router.js";
import { Drawer, Pager, Spinner, Empty, ErrorState, StaleBanner, Json } from "../lib/ui.js";
import { fmtDateTime } from "../lib/format.js";
import { toast } from "../lib/toast.js";
import { t } from "../lib/i18n.js";
import { sevLabel } from "../lib/labels.js";

export function IncidentsView({ query, params }) {
  const [filters, setFilter, reset, offset, setOffset] = useUrlFilters("/incidents", query, {
    state: "active", acknowledged: "", search: "", rule: "",
  });
  const [selected, setSelected] = useState(null);
  useEffect(() => { setSelected(params?.id || null); }, [params?.id]);
  const [data, , reload, error] = useLoader((signal) => api.get("/v1/incidents", {
    skip: offset, limit: 50, state: filters.state === "all" ? undefined : filters.state,
    acknowledged: filters.acknowledged || undefined, search: filters.search || undefined,
    rule_id: filters.rule || undefined,
  }, { signal }), [filters, offset]);
  const close = () => { setSelected(null); if (params?.id) navigate("/incidents", query, { force: true }); };
  return html`<div>
    <div class="page-head"><div><h1>${t("incidents.title")}</h1><p class="muted">${t("incidents.intro")}</p></div>
      <button class="btn" onClick=${reload}>${t("log.refresh")}</button></div>
    <div class="card filters">
      <select aria-label=${t("incidents.filterState")} value=${filters.state} onChange=${(e) => setFilter("state", e.target.value)}>
        <option value="all">${t("incidents.all")}</option><option value="active">${t("incidents.active")}</option><option value="resolved">${t("incidents.resolved")}</option>
      </select>
      <select aria-label=${t("incidents.filterAck")} value=${filters.acknowledged} onChange=${(e) => setFilter("acknowledged", e.target.value)}>
        <option value="">${t("log.anyAck")}</option><option value="false">${t("log.optUnacked")}</option><option value="true">${t("log.optAcked")}</option>
      </select>
      <input class="grow" aria-label=${t("incidents.search")} placeholder=${t("incidents.search")} value=${filters.search} onInput=${(e) => setFilter("search", e.target.value)} />
      <button class="btn sm" onClick=${reset}>${t("log.clear")}</button>
    </div>
    ${error && data ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    <div class="card" style="margin-top:14px; overflow-x:auto">
      ${error && !data ? html`<${ErrorState} error=${error} onRetry=${reload} />` : !data ? html`<${Spinner} />` : !data.items.length ? (filters.state === "active" && !filters.acknowledged && !filters.search && !filters.rule
        ? html`<${Empty} title=${t("incidents.blank.title")} body=${t("incidents.blank.body")} />`
        : html`<${Empty} filtered onClear=${reset} />`) : html`
        <table class="tbl"><thead><tr><th>${t("incidents.title")}</th><th>${t("log.sev")}</th><th>${t("log.status")}</th><th>${t("incidents.opened")}</th><th>${t("log.acked")}</th></tr></thead>
          <tbody>${data.items.map((i) => html`<tr key=${i.id}>
            <td><button class="cell-btn" onClick=${() => setSelected(i.id)}>${i.title}</button><div class="small muted mono">${i.rule_name}</div></td>
            <td><span class=${`badge plain ${i.severity}`}>${sevLabel(i.severity)}</span></td>
            <td><${IncidentState} incident=${i} /></td><td>${fmtDateTime(i.opened_at)}</td>
            <td>${i.acknowledged_at ? fmtDateTime(i.acknowledged_at) : "—"}</td>
          </tr>`)}</tbody></table>
        <${Pager} offset=${data.offset} limit=${data.limit} total=${data.total} onPage=${setOffset} />`}
    </div>
    ${selected ? html`<${IncidentDrawer} key=${selected} id=${selected} onClose=${close} onChanged=${reload} />` : null}
  </div>`;
}

function IncidentState({ incident }) {
  return html`<span class=${`badge plain ${incident.state === "active" ? "warning" : "ok"}`}>${t(`incidents.${incident.state}`)}</span>`;
}

function IncidentDrawer({ id, onClose, onChanged }) {
  const [data, , reload, error] = useLoader((signal) => api.get(`/v1/incidents/${encodeURIComponent(id)}`, null, { signal }), [id]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  async function act(action) {
    setBusy(true);
    try {
      await api.post(`/v1/incidents/${encodeURIComponent(id)}/${action}`, action === "resolve" ? { reason: reason.trim() } : undefined);
      setReason(""); reload(); onChanged?.();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }
  return html`<${Drawer} open=${true} title=${data?.title || t("incidents.title")} onClose=${onClose}>
    ${error && data ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    ${error && !data ? html`<${ErrorState} error=${error} onRetry=${reload} />` : !data ? html`<${Spinner} />` : html`
      <${IncidentState} incident=${data} />
      <dl class="kv">
        ${data.source_kind && data.source_kind !== "rule"
          ? html`<dt>${t("incidents.source")}</dt><dd>${t(`incidents.sourceKind.${data.source_kind}`)} · <span class="mono">${data.rule_name}</span></dd>`
          : html`<dt>${t("log.rule")}</dt><dd>${data.rule_id ? html`<a href=${`#/rules/${data.rule_id}`}>${data.rule_name}</a>` : data.rule_name}</dd>`}
        <dt>${t("incidents.opened")}</dt><dd>${fmtDateTime(data.opened_at)}</dd>
        <dt>${t("incidents.duration")}</dt><dd>${data.duration_sec}s</dd>
        <dt>${t("log.acked")}</dt><dd>${data.acknowledged_at ? `${fmtDateTime(data.acknowledged_at)} · ${data.acknowledged_by || ""}` : "—"}</dd>
        ${data.resolved_at ? html`<dt>${t("incidents.resolved")}</dt><dd>${fmtDateTime(data.resolved_at)}</dd><dt>${t("incidents.reason")}</dt><dd>${data.resolution_reason === "recovered" ? t("incidents.recovered") : data.resolution_reason === "rule_reconfigured" ? t("incidents.reconfigured") : data.resolution_reason === "superseded" ? t("incidents.superseded") : data.resolution_reason}</dd>` : null}
      </dl>
      <a class="btn sm" href=${`#/log?incident=${encodeURIComponent(id)}`}>${t("incidents.notifications")}</a>
      ${!data.acknowledged_at ? html`<button class="btn sm" disabled=${busy} onClick=${() => act("ack")}>${t("log.acknowledge")}</button>` : null}
      ${data.state === "active" ? html`<div class="field" style="margin-top:16px">
        <label for="incident-reason">${t("incidents.manualReason")}</label>
        <textarea id="incident-reason" maxLength="450" value=${reason} onInput=${(e) => setReason(e.target.value)}></textarea>
        <p class="muted small">${t("incidents.manualHelp")}</p>
        <button class="btn" disabled=${busy || !reason.trim()} onClick=${() => act("resolve")}>${t("incidents.manualResolve")}</button>
      </div>` : null}
      <h3 class="why-h">${t("incidents.openingValues")}</h3><${Json} value=${data.opening_context} />
      ${data.resolution_context ? html`<h3 class="why-h">${t("incidents.resolutionValues")}</h3><${Json} value=${data.resolution_context} />` : null}
    `}
  </${Drawer}>`;
}
