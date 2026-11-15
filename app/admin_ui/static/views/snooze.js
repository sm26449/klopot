// Snooze & maintenance (phase F4): active mutes + history, create by
// scope/target/until, and a one-click maintenance mode (snooze type:*).
import { html, useState, useEffect, useCallback } from "../lib/h.js";
import { api, getAll } from "../lib/api.js";
import { lookup } from "../lib/lookup.js";
import { toast } from "../lib/toast.js";
import { Spinner, Empty, ErrorState } from "../lib/ui.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import { t } from "../lib/i18n.js";

const SCOPES = ["type", "rule", "channel"];
const MAINT = { scope: "type", target: "*" };

function isoInHours(h) { return new Date(Date.now() + h * 3600 * 1000).toISOString(); }
function isMaintenance(s) { return s.target === "*"; }

export function SnoozeView() {
  const [active, setActive] = useState(null);
  const [history, setHistory] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [busy, setBusy] = useState(false);

  // Create form
  const [scope, setScope] = useState("type");
  const [target, setTarget] = useState("");
  const [until, setUntil] = useState("");
  const [reason, setReason] = useState("");
  const [opts, setOpts] = useState({ type: [], rule: [], channel: [] });
  const [errActive, setErrActive] = useState(null); // active-list load error (UX-006)

  const loadActive = useCallback(async () => {
    setErrActive(null);
    try { const p = await api.get("/v1/snooze", { active: "true", limit: 200 }); setActive(p.items); }
    catch (e) { setErrActive(e); }
  }, []);
  const loadHistory = useCallback(async () => {
    try { const p = await api.get("/v1/snooze", { active: "false", limit: 100 }); setHistory(p.items); }
    catch (e) { toast.error(e); }
  }, []);

  useEffect(() => { loadActive(); }, [loadActive]);
  useEffect(() => { if (showHistory && history === null) loadHistory(); }, [showHistory, history, loadHistory]);

  // Target autocomplete options per scope.
  useEffect(() => {
    Promise.all([
      lookup(getAll("/v1/templates").then((p) => p.items.map((t) => t.type)), []),
      lookup(getAll("/v1/rules").then((p) => p.items.map((r) => ({ id: r.id, name: r.name }))), []),
      lookup(getAll("/v1/channels").then((p) => p.items.map((c) => c.name)), []),
    ]).then(([type, rule, channel]) => setOpts({ type, rule, channel }));
  }, []);

  const maintenance = (active || []).find(isMaintenance);

  async function create(e) {
    e?.preventDefault();
    if (!target.trim()) return toast.error(t("snooze.targetRequired"));
    if (!until) return toast.error(t("snooze.pickEndTime"));
    setBusy(true);
    try {
      await api.post("/v1/snooze", {
        scope, target: target.trim(),
        until: new Date(until).toISOString(),
        reason: reason.trim() || null,
      });
      toast.ok(t("snooze.created"));
      setTarget(""); setReason(""); setUntil("");
      await loadActive(); if (showHistory) await loadHistory();
    } catch (err) { toast.error(err); } finally { setBusy(false); }
  }

  async function cancel(s) {
    if (!confirm(t("snooze.confirmCancel", { scope: s.scope, target: s.target }))) return;
    setBusy(true);
    try { await api.del(`/v1/snooze/${s.id}`); toast.ok(t("snooze.cancelled")); await loadActive(); if (showHistory) await loadHistory(); }
    catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  async function startMaintenance() {
    const hours = Number(prompt(t("snooze.maintPrompt"), "1"));
    if (!hours || hours <= 0) return;
    if (!confirm(t("snooze.confirmMuteAll", { hours }))) return;
    setBusy(true);
    try {
      await api.post("/v1/snooze", { ...MAINT, until: isoInHours(hours), reason: "maintenance mode" });
      toast.ok(t("snooze.maintOn", { hours })); await loadActive();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  function snoozeRow(s) {
    return html`<tr key=${s.id} class=${isMaintenance(s) ? "maint-row" : ""}>
      <td><span class="badge plain">${s.scope}</span></td>
      <td class="mono">${isMaintenance(s) ? html`<b>${t("snooze.allMaintenance")}</b>` : s.target}</td>
      <td title=${fmtDateTime(s.until)}>${fmtRelative(s.until)}</td>
      <td class="small muted">${s.reason || "—"}</td>
      <td class="small muted">${s.created_by || "—"}</td>
      <td>${active !== null ? html`<button class="btn sm danger" onClick=${() => cancel(s)} disabled=${busy}>${t("snooze.cancel")}</button>` : null}</td>
    </tr>`;
  }

  return html`<div>
    <div class="page-head">
      <div><h1>${t("snooze.title")}</h1><p class="muted">${t("snooze.subtitle")}</p></div>
      <div class="actions">
        ${maintenance
          ? html`<button class="btn danger" onClick=${() => cancel(maintenance)} disabled=${busy}>${t("snooze.endMaintenance")}</button>`
          : html`<button class="btn" onClick=${startMaintenance} disabled=${busy}>${t("snooze.maintenanceMode")}</button>`}
      </div>
    </div>

    ${maintenance ? html`<div class="alert crit"><b>${t("snooze.maintOnTitle")}</b> ${t("snooze.maintBannerBody")}
      ${fmtDateTime(maintenance.until)} (${fmtRelative(maintenance.until)}).</div>` : null}

    <div class="grid" style="grid-template-columns: 1fr; gap:14px">
      <div class="card">
        <h2>${t("snooze.newSnooze")}</h2>
        <form onSubmit=${create} class="snooze-form">
          <div class="field">
            <label for="sn-scope">${t("snooze.scope")}</label>
            <select id="sn-scope" value=${scope} onChange=${(e) => { setScope(e.target.value); setTarget(""); }}>
              ${SCOPES.map((s) => html`<option key=${s} value=${s}>${s}</option>`)}
            </select>
          </div>
          <div class="field">
            <label for="sn-target">${t("snooze.target")}</label>
            ${scope === "rule"
              ? html`<select id="sn-target" value=${target} onChange=${(e) => setTarget(e.target.value)}>
                  <option value="">${t("snooze.pickRule")}</option>
                  ${(opts.rule || []).map((r) => html`<option key=${r.id} value=${r.id}>${r.name}</option>`)}
                </select>`
              : html`<input id="sn-target" list="snooze-targets" value=${target} onInput=${(e) => setTarget(e.target.value)}
                   placeholder=${scope === "type" ? t("snooze.targetPlaceholder") : scope} />
                <datalist id="snooze-targets">${(opts[scope] || []).map((o) => html`<option key=${o} value=${o}></option>`)}</datalist>`}
          </div>
          <div class="field">
            <label for="sn-until">${t("snooze.until")}</label>
            <input id="sn-until" type="datetime-local" value=${until} onInput=${(e) => setUntil(e.target.value)} />
            <div class="quick">
              ${[1, 8, 24].map((h) => html`<button type="button" key=${h} class="btn sm ghost"
                onClick=${() => setUntil(toLocalInput(isoInHours(h)))}>+${h}h</button>`)}
            </div>
          </div>
          <div class="field grow">
            <label for="sn-reason">${t("snooze.reason")} <span class="muted small">${t("snooze.optional")}</span></label>
            <input id="sn-reason" value=${reason} onInput=${(e) => setReason(e.target.value)} placeholder=${t("snooze.whyMute")} />
          </div>
          <div class="form-actions"><button class="btn primary" disabled=${busy}>${t("snooze.createSnooze")}</button></div>
        </form>
      </div>

      <div class="card" style="padding:0">
        <div class="page-head" style="margin:0; padding:14px 18px 8px">
          <h2 style="margin:0">${t("snooze.activeSnoozes")}</h2>
          <div class="actions">
            <button class="btn sm" onClick=${loadActive}>${t("snooze.refresh")}</button>
            <button class="btn sm ghost" onClick=${() => setShowHistory((v) => !v)}>${showHistory ? t("snooze.hideHistory") : t("snooze.showHistory")}</button>
          </div>
        </div>
        ${errActive && active === null ? html`<${ErrorState} error=${errActive} onRetry=${loadActive} />` : active === null ? html`<${Spinner} />` : active.length === 0
          ? html`<${Empty} label=${t("snooze.emptyActive")} />`
          : html`<table class="tbl"><thead><tr><th>${t("snooze.scope")}</th><th>${t("snooze.target")}</th><th>${t("snooze.colEnds")}</th><th>${t("snooze.reason")}</th><th>${t("snooze.colBy")}</th><th><span class="sr-only">${t("common.actions")}</span></th></tr></thead>
              <tbody>${active.map(snoozeRow)}</tbody></table>`}

        ${showHistory ? html`<div class="hist">
          <div class="nav-title" style="padding:12px 18px 4px">${t("snooze.expiredCancelled")}</div>
          ${history === null ? html`<${Spinner} />` : history.length === 0
            ? html`<${Empty} label=${t("snooze.emptyHistory")} />`
            : html`<table class="tbl"><thead><tr><th>${t("snooze.scope")}</th><th>${t("snooze.target")}</th><th>${t("snooze.colEnded")}</th><th>${t("snooze.reason")}</th><th>${t("snooze.colBy")}</th><th><span class="sr-only">${t("common.actions")}</span></th></tr></thead>
                <tbody>${history.map((s) => html`<tr key=${s.id} class="muted">
                  <td><span class="badge plain">${s.scope}</span></td>
                  <td class="mono">${isMaintenance(s) ? t("snooze.all") : s.target}</td>
                  <td title=${fmtDateTime(s.until)}>${fmtRelative(s.until)}</td>
                  <td class="small">${s.reason || "—"}</td>
                  <td class="small">${s.created_by || "—"}</td><td></td>
                </tr>`)}</tbody></table>`}
        </div>` : null}
      </div>
    </div>
  </div>`;
}

// ISO (UTC) → value for <input type=datetime-local> in local time.
function toLocalInput(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
