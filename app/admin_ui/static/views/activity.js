// Activity (docs/ACTIVITY_LOG.md): what reached Klopot and what Klopot sent.
//
// Tabs (?tab=): requests · sources · attempts · events · rules. Filters live in
// the URL like every list. Bodies (request / response, exchanges) come from
// admin-only endpoints; a read-only key sees the metadata.
import { html, useState, useEffect } from "../lib/h.js";
import { api } from "../lib/api.js";
import { useLoader } from "../lib/loader.js";
import { navigate, useUrlFilters } from "../lib/router.js";
import { toast } from "../lib/toast.js";
import { Drawer, Spinner, Empty, ErrorState, StaleBanner, Pager, DangerConfirm } from "../lib/ui.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import { t } from "../lib/i18n.js";
import { useFieldErrors, FieldErrorSummary, FieldMsg } from "../lib/form.js";

const LIMIT = 50;
const TABS = ["requests", "sources", "attempts", "events", "rules"];
const STATUS_CLASSES = ["2xx", "3xx", "4xx", "5xx"];
const OUTCOMES = ["sent", "deferred", "failed", "permanent", "timeout"];
const BODY_MODES = ["auto", "never", "errors", "always"];

const statusTone = (s) => (s >= 500 ? "critical" : s >= 400 ? "warning" : s >= 300 ? "" : "ok");
const outcomeTone = (o) => ({ sent: "ok", deferred: "warning", failed: "critical", permanent: "critical", timeout: "critical" }[o] || "");

function StatusBadge({ status }) {
  return html`<span class=${`badge plain ${statusTone(status)}`}>${status}</span>`;
}

function Body({ label, text }) {
  if (!text) return null;
  let shown = text;
  try { shown = JSON.stringify(JSON.parse(text), null, 2); } catch { /* not JSON — show as is */ }
  return html`<div class="field"><div class="mini-h">${label}</div><pre class="json" tabindex="0">${shown}</pre></div>`;
}

export function ActivityView({ query, user }) {
  const tab = TABS.includes(query?.tab) ? query.tab : "requests";
  const go = (k) => navigate("/activity", { tab: k });
  return html`<div>
    <div class="page-head"><div><h1>${t("activity.title")}</h1><p class="muted">${t("activity.intro")}</p></div></div>
    <div class="tabs" role="tablist" aria-label=${t("activity.title")}>
      ${TABS.map((k) => html`<button key=${k} role="tab" type="button" class=${"tab" + (k === tab ? " active" : "")}
        aria-selected=${k === tab ? "true" : "false"} onClick=${() => go(k)}>${t(`activity.tab.${k}`)}</button>`)}
    </div>
    <div role="tabpanel">
      ${tab === "requests" ? html`<${RequestsTab} query=${query} admin=${user?.role === "admin"} />` : null}
      ${tab === "sources" ? html`<${SourcesTab} query=${query} />` : null}
      ${tab === "attempts" ? html`<${AttemptsTab} query=${query} />` : null}
      ${tab === "events" ? html`<${EventsTab} query=${query} />` : null}
      ${tab === "rules" ? html`<${RulesTab} admin=${user?.role === "admin"} />` : null}
    </div>
  </div>`;
}

// ── Requests ───────────────────────────────────────────────────────

function RequestsTab({ query, admin }) {
  const [filters, setF, reset, offset, setOffset] = useUrlFilters("/activity", query, {
    tab: "requests", method: "", status: "", search: "", actor: "", ip: "", webhooks: "",
  });
  const [selected, setSelected] = useState(null);
  const [data, , reload, error] = useLoader((signal) => {
    const q = { skip: offset, limit: LIMIT };
    for (const [k, v] of Object.entries(filters)) if (v && k !== "tab") q[k] = v;
    return api.get("/v1/activity/requests", q, { signal });
  }, [filters, offset]);
  const items = data?.items || [];
  const filtered = Object.entries(filters).some(([k, v]) => k !== "tab" && v);

  return html`
    <div class="card filters">
      <select aria-label=${t("activity.method")} value=${filters.method} onChange=${(e) => setF("method", e.target.value)}>
        <option value="">${t("activity.anyMethod")}</option>${["GET", "POST", "PATCH", "PUT", "DELETE"].map((m) => html`<option key=${m}>${m}</option>`)}</select>
      <select aria-label=${t("activity.status")} value=${filters.status} onChange=${(e) => setF("status", e.target.value)}>
        <option value="">${t("activity.anyStatus")}</option>${STATUS_CLASSES.map((s) => html`<option key=${s}>${s}</option>`)}</select>
      <input aria-label=${t("activity.searchPath")} placeholder=${t("activity.searchPath")} value=${filters.search} onInput=${(e) => setF("search", e.target.value)} />
      <input aria-label=${t("activity.actor")} placeholder=${t("activity.actor")} value=${filters.actor} onInput=${(e) => setF("actor", e.target.value)} />
      <input aria-label=${t("activity.ip")} placeholder=${t("activity.ip")} value=${filters.ip} onInput=${(e) => setF("ip", e.target.value)} />
      <label class="chk"><input type="checkbox" checked=${filters.webhooks === "true"} onChange=${(e) => setF("webhooks", e.target.checked ? "true" : "")} /> ${t("activity.onlyWebhooks")}</label>
      <button class="btn sm" onClick=${reload}>${t("activity.refresh")}</button>
    </div>
    ${error && data ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    <div class="card" style="margin-top:14px; padding:0">
      ${error && !data ? html`<${ErrorState} error=${error} onRetry=${reload} />` : data === null ? html`<${Spinner} />`
        : items.length === 0 ? (filtered ? html`<${Empty} filtered onClear=${reset} />` : html`<${Empty} label=${t("activity.noRequests")} />`)
        : html`<div class="scroll-x" tabindex="0"><table class="tbl"><thead><tr>
            <th>${t("activity.when")}</th><th>${t("activity.status")}</th><th>${t("activity.request")}</th><th>${t("activity.who")}</th><th>${t("activity.duration")}</th>
          </tr></thead><tbody>${items.map((r) => html`<tr key=${r.id} class="row-link" onClick=${() => setSelected(r)}>
            <td class="nowrap"><button type="button" class="cell-btn" title=${fmtDateTime(r.ts)} aria-description=${t("activity.openRequest")}
              onClick=${(e) => { e.stopPropagation(); setSelected(r); }}>${fmtRelative(r.ts)}</button></td>
            <td><${StatusBadge} status=${r.status} /></td>
            <td><span class="mono small">${r.method}</span> <span class="mono">${r.path}</span>
              ${r.has_request_body || r.has_response_body ? html` <span class="chip tag" title=${t("activity.hasBody")}>{ }</span>` : null}</td>
            <td class="small">${r.actor_name || html`<span class="muted">${t("activity.anonymous")}</span>`}<div class="muted mono">${r.client_ip || ""}</div></td>
            <td class="small nowrap">${r.duration_ms} ms</td>
          </tr>`)}</tbody></table></div>`}
    </div>
    ${data ? html`<${Pager} offset=${offset} limit=${LIMIT} total=${data.total} onPage=${setOffset} />` : null}
    ${selected ? html`<${RequestDrawer} row=${selected} admin=${admin} onClose=${() => setSelected(null)} />` : null}`;
}

function RequestDrawer({ row, admin, onClose }) {
  const [detail, setDetail] = useState(null);
  useEffect(() => {
    if (admin && (row.has_request_body || row.has_response_body)) {
      api.get(`/v1/activity/requests/${row.id}`).then(setDetail).catch((e) => toast.error(e));
    }
  }, [row.id]);
  return html`<${Drawer} open=${true} width=${720} title=${`${row.method} ${row.route}`} onClose=${onClose}>
    <div class="editor">
      <dl class="kv">
        <dt>${t("activity.when")}</dt><dd>${fmtDateTime(row.ts)}</dd>
        <dt>${t("activity.status")}</dt><dd><${StatusBadge} status=${row.status} /> · ${row.duration_ms} ms</dd>
        <dt>${t("activity.path")}</dt><dd class="mono">${row.path}</dd>
        <dt>${t("activity.who")}</dt><dd>${row.actor_name ? `${row.actor_name} (${row.actor_kind})` : t("activity.anonymous")}</dd>
        <dt>${t("activity.ip")}</dt><dd class="mono">${row.client_ip || "—"}</dd>
        <dt>${t("activity.userAgent")}</dt><dd class="small">${row.user_agent || "—"}</dd>
        <dt>${t("activity.traceId")}</dt><dd class="mono">${row.trace_id || "—"}</dd>
        <dt>${t("activity.keptUntil")}</dt><dd>${fmtDateTime(row.expires_at)}${row.rule_id ? html` <a href="#/activity?tab=rules">${t("activity.byRule")}</a>` : null}</dd>
      </dl>
      ${row.has_request_body || row.has_response_body ? (admin ? (detail ? html`
          <${Body} label=${t("activity.requestBody")} text=${detail.request_body} />
          <${Body} label=${t("activity.responseBody")} text=${detail.response_body} />` : html`<${Spinner} />`)
        : html`<p class="muted small">${t("activity.bodiesAdminOnly")}</p>`) : html`<p class="muted small">${t("activity.noBodies")}</p>`}
    </div>
  </${Drawer}>`;
}

// ── Sources ────────────────────────────────────────────────────────

function SourcesTab({ query }) {
  const [filters, setF] = useUrlFilters("/activity", query, { tab: "sources", hours: "24" });
  const [ruleDraft, setRuleDraft] = useState(null);
  const [data, , reload, error] = useLoader((signal) => api.get("/v1/activity/sources", { hours: filters.hours || 24 }, { signal }), [filters]);
  return html`
    <div class="card filters">
      <label for="src-hours">${t("activity.window")}</label>
      <select id="src-hours" value=${filters.hours} onChange=${(e) => setF("hours", e.target.value)}>
        ${[["1", "1h"], ["24", "24h"], ["168", "7d"], ["720", "30d"]].map(([v, l]) => html`<option key=${v} value=${v}>${l}</option>`)}</select>
      <button class="btn sm" onClick=${reload}>${t("activity.refresh")}</button>
    </div>
    ${error ? html`<${ErrorState} error=${error} onRetry=${reload} />` : !data ? html`<${Spinner} />` : html`
      <div class="card" style="margin-top:14px; padding:0">
        ${!data.sources.length ? html`<${Empty} label=${t("activity.noRequests")} />` : html`<div class="scroll-x" tabindex="0"><table class="tbl"><thead><tr>
          <th>${t("activity.who")}</th><th>${t("activity.request")}</th><th>${t("activity.count")}</th><th>${t("activity.byStatus")}</th><th>${t("activity.lastSeen")}</th><th><span class="sr-only">${t("common.actions")}</span></th>
        </tr></thead><tbody>${data.sources.map((s, i) => html`<tr key=${i}>
          <td class="small">${s.actor_name || html`<span class="muted">${t("activity.anonymous")}</span>`}<div class="muted mono">${s.client_ip || ""}</div></td>
          <td><span class="mono small">${s.method}</span> <a class="mono" href=${`#/activity?tab=requests&search=${encodeURIComponent(s.route.split("{")[0])}${s.actor_name ? "&actor=" + encodeURIComponent(s.actor_name) : ""}`}>${s.route}</a></td>
          <td>${s.total}</td>
          <td>${Object.entries(s.by_class).map(([k, v]) => html`<span key=${k} class=${`badge plain ${statusTone(Number(k[0]) * 100)}`}>${k} ${v}</span> `)}</td>
          <td class="small" title=${fmtDateTime(s.last_seen)}>${fmtRelative(s.last_seen)}</td>
          <td><button class="btn sm ghost" onClick=${() => setRuleDraft({ name: `${s.method} ${s.route}`.slice(0, 64), match_method: s.method, match_path: s.route.replace(/\{[^}]+\}/g, "*"), action: "ignore" })}>${t("activity.makeRule")}</button></td>
        </tr>`)}</tbody></table></div>`}
      </div>
      ${data.ignored.length ? html`<div class="card" style="margin-top:14px">
        <h2>${t("activity.ignoredTitle")}</h2><p class="muted small">${t("activity.ignoredHelp")}</p>
        <table class="tbl"><thead><tr><th>${t("activity.rule")}</th><th>${t("activity.pattern")}</th><th>${t("activity.count")}</th><th>${t("activity.lastSeen")}</th></tr></thead>
        <tbody>${data.ignored.map((g) => html`<tr key=${g.rule_id}><td>${g.name}</td><td class="mono small">${g.pattern}</td><td>${g.hits}</td>
          <td class="small">${g.last_hit_at ? html`<span title=${fmtDateTime(g.last_hit_at)}>${fmtRelative(g.last_hit_at)}</span> <span class="muted mono">${g.last_ip || ""}</span>` : "—"}</td></tr>`)}</tbody></table>
      </div>` : null}`}
    ${ruleDraft ? html`<${RuleEditor} rule=${ruleDraft} onClose=${() => setRuleDraft(null)} onSaved=${() => { setRuleDraft(null); navigate("/activity", { tab: "rules" }); }} />` : null}`;
}

// ── Attempts ───────────────────────────────────────────────────────

// Bodies show when the server sent them (it strips them for read-only callers).
export function AttemptList({ items, compact = false }) {
  const [open, setOpen] = useState(null);
  if (!items.length) return html`<p class="muted small">${t("activity.noAttempts")}</p>`;
  return html`<ol class="attempts">${items.map((a) => html`<li key=${a.id}>
    <div class="attempt-head">
      <span class=${`badge plain ${outcomeTone(a.outcome)}`}>${t(`activity.outcome.${a.outcome}`)}</span>
      ${compact ? null : html`<b>${a.channel}</b>`}
      ${a.kind !== "alert" ? html`<span class="chip tag">${t(`activity.kind.${a.kind}`)}</span>` : null}
      ${a.http_status ? html`<${StatusBadge} status=${a.http_status} />` : null}
      <span class="muted small" title=${fmtDateTime(a.started_at)}>${fmtRelative(a.started_at)} · ${a.duration_ms} ms</span>
      ${a.retry_after_sec ? html`<span class="small">${t("activity.waited", { sec: a.retry_after_sec })}</span>` : null}
      ${a.exchange?.length ? html`<button type="button" class="link-btn small" aria-expanded=${open === a.id ? "true" : "false"}
        onClick=${() => setOpen(open === a.id ? null : a.id)}>${open === a.id ? t("activity.hideExchange") : t("activity.showExchange")}</button>` : null}
    </div>
    ${a.error ? html`<div class="small error">${a.error}</div>` : null}
    ${open === a.id ? html`<div class="exchange">${a.exchange.map((x, i) => html`<div key=${i} class="exchange-item">
      <div class="mono small"><b>${x.method}</b> ${x.url} → ${x.status ?? x.error ?? "—"} · ${x.duration_ms} ms
        ${x.response_headers ? Object.entries(x.response_headers).map(([k, v]) => html` <span key=${k} class="chip">${k}: ${v}</span>`) : null}</div>
      ${"request_body" in x || "response_body" in x
        ? html`<${Body} label=${t("activity.requestBody")} text=${x.request_body} /><${Body} label=${t("activity.responseBody")} text=${x.response_body} />`
        : html`<p class="muted small">${t("activity.bodiesAdminOnly")}</p>`}
    </div>`)}</div>` : null}
  </li>`)}</ol>`;
}

function AttemptsTab({ query }) {
  const [filters, setF, reset, offset, setOffset] = useUrlFilters("/activity", query, { tab: "attempts", channel: "", outcome: "", kind: "" });
  const [data, , reload, error] = useLoader((signal) => {
    const q = { skip: offset, limit: LIMIT };
    for (const [k, v] of Object.entries(filters)) if (v && k !== "tab") q[k] = v;
    return api.get("/v1/activity/attempts", q, { signal });
  }, [filters, offset]);
  const filtered = filters.channel || filters.outcome || filters.kind;
  return html`
    <div class="card filters">
      <input aria-label=${t("activity.channel")} placeholder=${t("activity.channel")} value=${filters.channel} onInput=${(e) => setF("channel", e.target.value)} />
      <select aria-label=${t("activity.outcomeLabel")} value=${filters.outcome} onChange=${(e) => setF("outcome", e.target.value)}>
        <option value="">${t("activity.anyOutcome")}</option>${OUTCOMES.map((o) => html`<option key=${o} value=${o}>${t(`activity.outcome.${o}`)}</option>`)}</select>
      <select aria-label=${t("activity.kindLabel")} value=${filters.kind} onChange=${(e) => setF("kind", e.target.value)}>
        <option value="">${t("activity.anyKind")}</option>${["alert", "escalation", "test"].map((k) => html`<option key=${k} value=${k}>${t(`activity.kind.${k}`)}</option>`)}</select>
      <button class="btn sm" onClick=${reload}>${t("activity.refresh")}</button>
    </div>
    <div class="card" style="margin-top:14px">
      ${error ? html`<${ErrorState} error=${error} onRetry=${reload} />` : !data ? html`<${Spinner} />`
        : !data.items.length && filtered ? html`<${Empty} filtered onClear=${reset} />` : html`<${AttemptList} items=${data.items} />`}
    </div>
    ${data ? html`<${Pager} offset=${offset} limit=${LIMIT} total=${data.total} onPage=${setOffset} />` : null}`;
}

// ── Events ─────────────────────────────────────────────────────────

function EventsTab({ query }) {
  const [filters, setF, reset, offset, setOffset] = useUrlFilters("/activity", query, { tab: "events", source_kind: "", source_name: "" });
  const [data, , reload, error] = useLoader((signal) => {
    const q = { skip: offset, limit: LIMIT };
    for (const [k, v] of Object.entries(filters)) if (v && k !== "tab") q[k] = v;
    return api.get("/v1/activity/events", q, { signal });
  }, [filters, offset]);
  const items = data?.items || [];
  return html`
    <div class="card filters">
      <select aria-label=${t("activity.sourceKind")} value=${filters.source_kind} onChange=${(e) => setF("source_kind", e.target.value)}>
        <option value="">${t("activity.anySource")}</option>${["input", "rule", "channel"].map((k) => html`<option key=${k} value=${k}>${t(`activity.source.${k}`)}</option>`)}</select>
      <input aria-label=${t("activity.name")} placeholder=${t("activity.name")} value=${filters.source_name} onInput=${(e) => setF("source_name", e.target.value)} />
      <button class="btn sm" onClick=${reload}>${t("activity.refresh")}</button>
    </div>
    <div class="card" style="margin-top:14px; padding:0">
      ${error ? html`<${ErrorState} error=${error} onRetry=${reload} />` : !data ? html`<${Spinner} />`
        : !items.length ? (filters.source_kind || filters.source_name ? html`<${Empty} filtered onClear=${reset} />` : html`<${Empty} label=${t("activity.noEvents")} />`)
        : html`<div class="scroll-x" tabindex="0"><table class="tbl"><thead><tr><th>${t("activity.when")}</th><th>${t("activity.sourceKind")}</th><th>${t("activity.name")}</th><th>${t("activity.event")}</th><th>${t("activity.detail")}</th></tr></thead>
          <tbody>${items.map((e) => html`<tr key=${e.id}>
            <td class="nowrap small" title=${fmtDateTime(e.ts)}>${fmtRelative(e.ts)}</td>
            <td class="small">${t(`activity.source.${e.source_kind}`)}</td><td class="mono small">${e.source_name}</td>
            <td><span class=${`badge plain ${/error|disconnected|open|disabled/.test(e.event) ? "warning" : "ok"}`}>${t(`activity.eventName.${e.event}`)}</span></td>
            <td class="small">${e.detail || ""}</td></tr>`)}</tbody></table></div>`}
    </div>
    ${data ? html`<${Pager} offset=${offset} limit=${LIMIT} total=${data.total} onPage=${setOffset} />` : null}`;
}

// ── Rules ──────────────────────────────────────────────────────────

function RulesTab({ admin }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  async function load() {
    try { setRows(await api.get("/v1/activity/rules")); setError(null); } catch (e) { setError(e); }
  }
  useEffect(() => { load(); }, []);
  return html`
    <div class="card">
      <div class="setup-card-head"><h2>${t("activity.rulesTitle")}</h2>
        ${admin ? html`<button class="btn primary sm" onClick=${() => setEditing({ __new: true })}>${t("activity.newRule")}</button>` : null}</div>
      <p class="muted small">${t("activity.rulesHelp")}</p>
      ${error ? html`<${ErrorState} error=${error} onRetry=${load} />` : !rows ? html`<${Spinner} />` : !rows.length ? html`<p class="muted">${t("activity.noRules")}</p>` : html`
        <div class="scroll-x" tabindex="0"><table class="tbl"><thead><tr><th>#</th><th>${t("activity.rule")}</th><th>${t("activity.pattern")}</th><th>${t("activity.actionLabel")}</th><th>${t("activity.bodies")}</th><th>${t("activity.count")}</th></tr></thead>
        <tbody>${rows.map((r, i) => html`<tr key=${r.id} class=${r.enabled ? "" : "muted"}>
          <td title=${t("activity.positionTitle", { n: r.position })}>${i + 1}</td>
          <td>${admin ? html`<button type="button" class="link-btn" onClick=${() => setEditing(r)}>${r.name}</button>` : r.name}${r.enabled ? null : html` <span class="chip">${t("activity.disabled")}</span>`}</td>
          <td class="mono small">${r.match_method || "*"} ${r.match_path}${r.match_status ? " " + r.match_status : ""}${r.match_actor ? " actor=" + r.match_actor : ""}${r.match_ip ? " ip=" + r.match_ip : ""}</td>
          <td>${r.action === "ignore" ? html`<span class="badge plain warning">${t("activity.action.ignore")}</span>` : html`<span class="badge plain">${r.keep_days ? keepDaysText(r.keep_days) : t("activity.action.keep")}</span>`}</td>
          <td class="small">${t(`activity.bodyMode.${r.request_body}`)} / ${t(`activity.bodyMode.${r.response_body}`)}</td>
          <td class="small">${r.hits}${r.last_hit_at ? html` <span class="muted" title=${fmtDateTime(r.last_hit_at)}>· ${fmtRelative(r.last_hit_at)}</span>` : null}</td>
        </tr>`)}</tbody></table></div>`}
    </div>
    ${editing ? html`<${RuleEditor} rule=${editing} onClose=${() => setEditing(null)} onSaved=${() => { setEditing(null); load(); }} />` : null}`;
}

// "keep 1 day" / "keep 5 days"; Romanian adds "de" from 20 on ("90 de zile").
export function keepDaysText(n) {
  const key = n === 1 ? "activity.keepDay" : (n % 100 === 0 || n % 100 >= 20) ? "activity.keepDaysMany" : "activity.keepDays";
  return t(key, { n });
}

const EMPTY_RULE = { name: "", enabled: true, position: 100, match_method: "", match_path: "*", match_status: "",
  match_actor: "", match_ip: "", action: "keep", keep_days: "", request_body: "auto", response_body: "auto" };

function RuleEditor({ rule, onClose, onSaved }) {
  const isNew = !rule.id;
  const [r, setR] = useState(() => ({ ...EMPTY_RULE, ...Object.fromEntries(Object.entries(rule).map(([k, v]) => [k, v ?? ""])) }));
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const fe = useFieldErrors();
  const set = (k, v) => { setR((cur) => ({ ...cur, [k]: v })); setPreview(null); };
  const payload = () => ({
    name: r.name.trim(), enabled: !!r.enabled, position: Number(r.position) || 100, match_method: r.match_method || null,
    match_path: r.match_path.trim() || "*", match_status: r.match_status || null, match_actor: r.match_actor.trim() || null,
    match_ip: r.match_ip.trim() || null, action: r.action, keep_days: r.action === "keep" && r.keep_days !== "" ? Number(r.keep_days) : null,
    request_body: r.request_body, response_body: r.response_body,
  });
  async function doPreview() {
    try { setPreview(await api.post("/v1/activity/rules/preview", { ...payload(), name: payload().name || "preview" })); } catch (e) { if (!fe.show(e)) toast.error(e); }
  }
  async function save() {
    fe.clear();
    if (!fe.check([["name", r.name.trim()]])) return;
    setBusy(true);
    try {
      if (isNew) await api.post("/v1/activity/rules", payload());
      else await api.patch(`/v1/activity/rules/${rule.id}`, payload());
      toast.ok(t("activity.ruleSaved"));
      onSaved();
    } catch (e) { if (!fe.show(e)) toast.error(e); } finally { setBusy(false); }
  }
  async function remove() {
    try { await api.del(`/v1/activity/rules/${rule.id}`); toast.ok(t("activity.ruleDeleted")); onSaved(); } catch (e) { toast.error(e); }
  }
  return html`<${Drawer} open=${true} width=${640} title=${isNew ? t("activity.newRule") : rule.name} onClose=${onClose}>
    <${FieldErrorSummary} errors=${fe.errors} idFor=${(f) => "ar-" + f.split(".").pop()} />
    <div class="editor">
      <p class="muted small">${t("activity.ruleHelp")}</p>
      <div class="row2">
        <div class="field"><label for="ar-name">${t("activity.ruleName")} <span class="req">*</span></label>
          <input id="ar-name" value=${r.name} onInput=${(e) => set("name", e.target.value)} ...${fe.attrs("name")} /><${FieldMsg} fe=${fe} name="name" /></div>
        <div class="field"><label for="ar-position">${t("activity.position")}</label>
          <input id="ar-position" type="number" value=${r.position} onInput=${(e) => set("position", e.target.value)} />
          <div class="hint">${t("activity.positionHint")}</div></div>
      </div>
      <fieldset class="gate"><legend>${t("activity.matchLegend")}</legend>
        <div class="row2">
          <div class="field"><label for="ar-match_method">${t("activity.method")}</label>
            <select id="ar-match_method" value=${r.match_method} onChange=${(e) => set("match_method", e.target.value)}>
              <option value="">${t("activity.anyMethod")}</option>${["GET", "POST", "PATCH", "PUT", "DELETE"].map((m) => html`<option key=${m}>${m}</option>`)}</select></div>
          <div class="field"><label for="ar-match_status">${t("activity.status")}</label>
            <input id="ar-match_status" placeholder="4xx" value=${r.match_status} onInput=${(e) => set("match_status", e.target.value)} ...${fe.attrs("match_status")} />
            <${FieldMsg} fe=${fe} name="match_status" /></div>
        </div>
        <div class="field"><label for="ar-match_path">${t("activity.pathPattern")}</label>
          <input id="ar-match_path" class="mono" value=${r.match_path} onInput=${(e) => set("match_path", e.target.value)} placeholder="/v1/health*" />
          <div class="hint">${t("activity.pathHint")}</div></div>
        <div class="row2">
          <div class="field"><label for="ar-match_actor">${t("activity.actor")}</label>
            <input id="ar-match_actor" value=${r.match_actor} onInput=${(e) => set("match_actor", e.target.value)} placeholder="backup-script*" /></div>
          <div class="field"><label for="ar-match_ip">${t("activity.ip")}</label>
            <input id="ar-match_ip" class="mono" value=${r.match_ip} onInput=${(e) => set("match_ip", e.target.value)} placeholder="10.0.0.*" /></div>
        </div>
      </fieldset>
      <fieldset class="gate"><legend>${t("activity.whatToDo")}</legend>
        <div class="row2">
          <div class="field"><label for="ar-action">${t("activity.actionLabel")}</label>
            <select id="ar-action" value=${r.action} onChange=${(e) => set("action", e.target.value)}>
              ${["keep", "ignore"].map((a) => html`<option key=${a} value=${a}>${t(`activity.actionLong.${a}`)}</option>`)}</select></div>
          ${r.action === "keep" ? html`<div class="field"><label for="ar-keep_days">${t("activity.keepFor")}</label>
            <input id="ar-keep_days" type="number" min="1" value=${r.keep_days} placeholder=${t("activity.keepDefault")} onInput=${(e) => set("keep_days", e.target.value)} />
            <div class="hint">${t("activity.keepHint")}</div></div>` : null}
        </div>
        ${r.action === "keep" ? html`<div class="row2">
          ${["request_body", "response_body"].map((k) => html`<div key=${k} class="field"><label for=${"ar-" + k}>${t(`activity.${k}`)}</label>
            <select id=${"ar-" + k} value=${r[k]} onChange=${(e) => set(k, e.target.value)}>
              ${BODY_MODES.map((m) => html`<option key=${m} value=${m}>${t(`activity.bodyModeLong.${m}`)}</option>`)}</select></div>`)}
        </div>` : html`<p class="hint">${t("activity.ignoreHint")}</p>`}
      </fieldset>
      <label class="chk"><input type="checkbox" checked=${!!r.enabled} onChange=${(e) => set("enabled", e.target.checked)} /> ${t("activity.enabled")}</label>
      <div class="form-actions">
        <button class="btn" type="button" onClick=${doPreview}>${t("activity.preview")}</button>
        ${preview ? html`<span class="small" role="status">${t("activity.previewResult", { matched: preview.matched, checked: preview.checked, hours: preview.window_hours })}</span>` : null}
      </div>
      <div class="editor-actions">
        <button class="btn primary" disabled=${busy} onClick=${save}>${isNew ? t("activity.create") : t("activity.save")}</button>
        ${!isNew ? html`<span class="spacer"></span><button class="btn danger" onClick=${() => setConfirmDel(true)}>${t("activity.delete")}</button>` : null}
      </div>
    </div>
    <${DangerConfirm} open=${confirmDel} token=${rule.name || ""} title=${t("activity.deleteTitle", { name: rule.name || "" })}
      onConfirm=${remove} onClose=${() => setConfirmDel(false)} />
  </${Drawer}>`;
}

// ── Small panels for other editors ────────────────────────────────

/** The last attempts of one channel (channel editor). */
export function ChannelActivity({ name, refresh }) {
  const [items, setItems] = useState(null);
  useEffect(() => {
    api.get("/v1/activity/attempts", { channel: name, limit: 5 }).then((p) => setItems(Array.isArray(p?.items) ? p.items : [])).catch(() => setItems(false));
  }, [name, refresh]);
  return html`<div class="field">
    <div class="mini-h">${t("activity.recentAttempts")} · <a href=${`#/activity?tab=attempts&channel=${encodeURIComponent(name)}`}>${t("activity.seeAll")}</a></div>
    ${items === null ? html`<${Spinner} />` : items === false ? html`<p class="muted small" role="status">${t("common.loadError")}</p>`
      : html`<${AttemptList} items=${items} compact=${true} />`}
  </div>`;
}

/** The last requests an inbound input received (input editor). */
export function InputPayloads({ inputId }) {
  const path = `/v1/inputs/${inputId}/webhook`;
  const [items, setItems] = useState(null);
  useEffect(() => {
    api.get("/v1/activity/requests", { search: path, limit: 5 }).then((p) => setItems(Array.isArray(p?.items) ? p.items : [])).catch(() => setItems(false));
  }, [inputId]);
  return html`<div class="field">
    <div class="mini-h">${t("activity.recentPayloads")} · <a href=${`#/activity?tab=requests&search=${encodeURIComponent(path)}`}>${t("activity.seeAll")}</a></div>
    ${items === null ? html`<${Spinner} />` : items === false ? html`<p class="muted small" role="status">${t("common.loadError")}</p>` : !items.length ? html`<p class="muted small">${t("activity.noPayloads")}</p>`
      : html`<ul class="setup-channels">${items.map((r) => html`<li key=${r.id}>
          <${StatusBadge} status=${r.status} /> <span class="small" title=${fmtDateTime(r.ts)}>${fmtRelative(r.ts)}</span>
          <span class="muted mono small">${r.client_ip || ""}</span>${r.has_request_body ? html` <span class="chip tag">{ }</span>` : null}</li>`)}</ul>`}
  </div>`;
}

