// Dashboard (phase F4): health, 24h stats, inventory counts, unacked
// criticals (quick ack) and active snoozes.
import { html, useState, useEffect, useCallback } from "../lib/h.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { Spinner, ErrorState } from "../lib/ui.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import { t } from "../lib/i18n.js";
import { sevLabel, statusLabel, reasonLabel, componentLabel, healthDetail } from "../lib/labels.js";
import { SetupCard } from "./setup.js";

const SEV_CLASS = { info: "", warning: "warning", critical: "critical" };

async function total(path, query) {
  const p = await api.get(path, { ...query, limit: 1 });
  return p.total;
}

export function DashboardView({ health, healthError, refreshHealth, user }) {
  const [stats, setStats] = useState(null);
  const [inv, setInv] = useState(null);
  const [criticals, setCriticals] = useState(null);
  const [snoozes, setSnoozes] = useState(null);
  // Each panel loads independently with its own error + retry, so one failing
  // endpoint no longer leaves the whole dashboard stuck (audit UX-006).
  const [errStats, setErrStats] = useState(null);
  const [errInv, setErrInv] = useState(null);
  const [errCrit, setErrCrit] = useState(null);
  const [errSnz, setErrSnz] = useState(null);

  const loadStats = useCallback(async () => {
    setErrStats(null);
    try { setStats(await api.get("/v1/log/stats", { window: "24h" })); } catch (e) { setErrStats(e); }
  }, []);
  const loadInv = useCallback(async () => {
    setErrInv(null);
    try {
      // Only ENABLED rules that are erroring are current incidents — a disabled
      // rule's frozen historical error must not inflate this (V21).
      const [rulesT, rulesEn, rulesErr, tmpl, chan, inp, sched] = await Promise.all([
        total("/v1/rules"), total("/v1/rules", { enabled: "true" }),
        total("/v1/rules", { has_error: "true", enabled: "true" }),
        total("/v1/templates"), total("/v1/channels"), total("/v1/inputs"), total("/v1/schedules"),
      ]);
      setInv({ rulesT, rulesEn, rulesErr, tmpl, chan, inp, sched });
    } catch (e) { setErrInv(e); }
  }, []);
  const loadCriticals = useCallback(async () => {
    setErrCrit(null);
    try { setCriticals((await api.get("/v1/log", { severity: "critical", acknowledged: "false", suppressed: "false", limit: 8 })).items); }
    catch (e) { setErrCrit(e); }
  }, []);
  const loadSnoozes = useCallback(async () => {
    setErrSnz(null);
    try { setSnoozes((await api.get("/v1/snooze", { active: "true", limit: 50 })).items); } catch (e) { setErrSnz(e); }
  }, []);
  const load = useCallback(() => { loadStats(); loadInv(); loadCriticals(); loadSnoozes(); },
    [loadStats, loadInv, loadCriticals, loadSnoozes]);

  useEffect(() => { load(); }, [load]);

  async function ack(id) {
    try { await api.post(`/v1/log/${encodeURIComponent(id)}/ack`); toast.ok(t("dashboard.acknowledged")); loadCriticals(); loadStats(); }
    catch (e) { toast.error(e); }
  }

  const comps = health?.components || {};
  const maint = (snoozes || []).find((s) => s.target === "*");

  return html`<div>
    <div class="page-head">
      <div><h1>${t("dashboard.title")}</h1><p class="muted">${t("dashboard.subtitle")}</p></div>
      <div class="actions"><button class="btn sm" onClick=${() => { load(); refreshHealth?.(); }}>${t("dashboard.refresh")}</button></div>
    </div>

    ${maint ? html`<div class="alert crit"><b>${t("dashboard.maintOn")}</b> ${t("dashboard.maintMuted")}
      ${fmtDateTime(maint.until)}. <a href="#/snooze">${t("dashboard.manage")}</a></div>` : null}

    <!-- An unfinished install shows what is left to do (the setup guide's
         checklist) instead of a misleading all-zero "all clear" (audit UX-023). -->
    <${SetupCard} user=${user} />

    <!-- Stat tiles -->
    <div class="tiles">
      ${errStats ? html`<${ErrorState} error=${errStats} onRetry=${loadStats} />` : stats ? html`
        <div class="tile"><div class="tile-n">${stats.dispatched}</div><div class="tile-l">${t("dashboard.tileDispatched")}</div></div>
        <div class="tile"><div class="tile-n">${stats.suppressed}</div><div class="tile-l">${t("dashboard.tileSuppressed")}</div></div>
        <div class="tile ${stats.unacked_critical > 0 ? "crit" : ""}"><div class="tile-n">${stats.unacked_critical}</div><div class="tile-l">${t("dashboard.tileUnackedCritical")}</div></div>
        <div class="tile"><div class="tile-n">${errSnz ? "—" : snoozes === null ? "…" : snoozes.length}</div><div class="tile-l">${t("dashboard.tileActiveSnoozes")}</div></div>
      ` : html`<${Spinner} />`}
    </div>

    <div class="grid" style="margin-top:4px">
      <!-- Service health -->
      <div class="card">
        <h2>${t("dashboard.service")}</h2>
        ${health ? html`<dl class="kv">
          <dt>${t("dashboard.status")}</dt><dd><span class="badge ${health.status}">${statusLabel(health.status)}</span></dd>
          <dt>${t("dashboard.version")}</dt><dd class="mono">${health.version}</dd>
          ${Object.entries(comps).map(([name, c]) => html`
            <dt key=${name}>${componentLabel(name)}</dt>
            <dd><span class="badge ${c.status}">${statusLabel(c.status)}</span>${healthDetail(c) ? html` <span class="muted small">${healthDetail(c)}</span>` : null}</dd>`)}
        </dl>` : healthError ? html`<${ErrorState} error=${healthError} onRetry=${refreshHealth} />` : html`<${Spinner} />`}
      </div>

      <!-- Inventory -->
      <div class="card">
        <h2>${t("dashboard.inventory")}</h2>
        ${errInv ? html`<${ErrorState} error=${errInv} onRetry=${loadInv} />` : inv ? html`<dl class="kv">
          <dt>${t("dashboard.rules")}</dt><dd>${inv.rulesEn}/${inv.rulesT} ${t("dashboard.rulesEnabled")}${inv.rulesErr ? html` · <a href="#/rules?eval_status=error&enabled=true" class="badge warning plain">${inv.rulesErr} ${t("dashboard.withErrors")}</a>` : ""}</dd>
          <dt>${t("dashboard.templates")}</dt><dd>${inv.tmpl}</dd>
          <dt>${t("dashboard.channels")}</dt><dd>${inv.chan}</dd>
          <dt>${t("dashboard.inputs")}</dt><dd>${inv.inp}</dd>
          <dt>${t("dashboard.schedules")}</dt><dd>${inv.sched}</dd>
        </dl>` : html`<${Spinner} />`}
      </div>

      <!-- 24h breakdown -->
      <div class="card">
        <h2>${t("dashboard.last24h")}</h2>
        ${errStats ? html`<${ErrorState} error=${errStats} onRetry=${loadStats} />` : stats ? html`
          <div class="mini-h">${t("dashboard.bySeverity")}</div>
          ${["critical", "warning", "info"].map((s) => html`<${Bar} key=${s} label=${sevLabel(s)} cls=${SEV_CLASS[s]}
              value=${stats.by_severity?.[s] || 0} max=${barMax(stats.by_severity)} />`)}
          ${Object.keys(stats.suppressed_by_reason || {}).length ? html`<div class="mini-h" style="margin-top:10px">${t("dashboard.suppressedByReason")}</div>
            ${Object.entries(stats.suppressed_by_reason).map(([k, v]) => html`<${Bar} key=${k} label=${reasonLabel(k)} value=${v} max=${barMax(stats.suppressed_by_reason)} />`)}` : null}
          ${(stats.top_types || []).length ? html`<div class="mini-h" style="margin-top:10px">${t("dashboard.busiestTypes")}</div>
            <dl class="kv small">${stats.top_types.slice(0, 5).map((t) => html`<dt key=${t.type} class="mono">${t.type}</dt><dd>${t.count}</dd>`)}</dl>` : null}
        ` : html`<${Spinner} />`}
      </div>

      <!-- Unacked criticals -->
      <div class="card">
        <h2>${t("dashboard.unackedCriticals")} <span class="muted small">${t("dashboard.allTime")}</span></h2>
        ${errCrit ? html`<${ErrorState} error=${errCrit} onRetry=${loadCriticals} />` : criticals === null ? html`<${Spinner} />` : criticals.length === 0
          ? html`<p class="muted">${t("dashboard.noneAllClear")}</p>`
          : html`<ul class="crit-list">${criticals.map((r) => html`<li key=${r.id}>
              <div class="crit-main">
                <a href=${`#/log?search=${encodeURIComponent(r.type)}`}>${r.title}</a>
                <div class="small muted"><span title=${fmtDateTime(r.fired_at)}>${fmtRelative(r.fired_at)}</span> · <span class="mono">${r.type}</span></div>
              </div>
              <button class="btn sm" onClick=${() => ack(r.id)}>${t("dashboard.ack")}</button>
            </li>`)}</ul>`}
      </div>

      <!-- Active snoozes -->
      <div class="card">
        <h2>${t("dashboard.activeSnoozes")}</h2>
        ${errSnz ? html`<${ErrorState} error=${errSnz} onRetry=${loadSnoozes} />` : snoozes === null ? html`<${Spinner} />` : snoozes.length === 0
          ? html`<p class="muted">${t("dashboard.none")} <a href="#/snooze">${t("dashboard.addOne")}</a></p>`
          : html`<table class="tbl"><tbody>${snoozes.map((s) => html`<tr key=${s.id}>
              <td><span class="badge plain">${s.scope}</span></td>
              <td class="mono">${s.target === "*" ? html`<b>${t("dashboard.all")}</b>` : s.target}</td>
              <td title=${fmtDateTime(s.until)}>${fmtRelative(s.until)}</td>
            </tr>`)}</tbody></table>
            <p style="margin-top:8px"><a href="#/snooze">${t("dashboard.manageSnoozes")}</a></p>`}
      </div>

      <!-- Links -->
      <div class="card">
        <h2>${t("dashboard.links")}</h2>
        <p><a href="#/api">${t("dashboard.openapi")}</a></p>
        <p><a href="/v1/metrics" target="_blank" rel="noopener">${t("dashboard.prometheus")}</a></p>
      </div>
    </div>
  </div>`;
}

function barMax(obj) { return Math.max(1, ...Object.values(obj || {})); }

function Bar({ label, value, max, cls }) {
  const pct = Math.round((value / max) * 100);
  return html`<div class="bar-row">
    <span class="bar-label">${label}</span>
    <span class="bar-track"><span class="bar-fill ${cls || ""}" style=${`width:${pct}%`}></span></span>
    <span class="bar-val mono">${value}</span>
  </div>`;
}
