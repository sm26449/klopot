// Operational queues and workers, read-only and refreshed every 10 seconds.
import { html, useEffect, useState } from "../lib/h.js";
import { api } from "../lib/api.js";
import { Spinner, Empty, ErrorState } from "../lib/ui.js";
import { fmtSeconds, fmtDateTime } from "../lib/format.js";
import { t } from "../lib/i18n.js";

export function OperationsView() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [nonce, reload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    const tick = async () => {
      try {
        const snapshot = await api.get("/v1/operations", null, { signal: controller.signal });
        if (!controller.signal.aborted) { setData(snapshot); setError(null); }
      } catch (e) { if (!controller.signal.aborted) setError(e); }
      if (!controller.signal.aborted) timer = setTimeout(tick, 10000);
    };
    tick();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [nonce]);
  const connections = [...(data?.telegram || []).map((c) => ({ ...c, kind: "Telegram" })),
    ...(data?.mqtt || []).map((c) => ({ ...c, kind: "MQTT" }))];
  return html`<div>
    <div class="page-head"><div><h1>${t("ops.title")}</h1><p class="muted">${t("ops.subtitle")}</p></div>
      <button class="btn" onClick=${() => reload((n) => n + 1)}>${t("ops.refresh")}</button></div>
    ${error && data ? html`<p class="muted" role="status">${t("common.refreshFailed")}</p>` : null}
    ${!data ? (error ? html`<${ErrorState} error=${error} onRetry=${() => reload((n) => n + 1)} />` : html`<${Spinner} />`) : html`
      <div class="card"><h2>${t("ops.workers")}</h2><div class="actions">
        ${Object.entries(data.workers).map(([name, alive]) => html`<span key=${name} class=${"badge " + (alive ? "ok" : "danger")}>
          ${t("ops.worker." + name)}: ${t(alive ? "ops.running" : "ops.stopped")}</span>`)}
      </div></div>
      <div class="card scroll-x" tabindex="0" role="region" aria-label=${t("ops.queues")} style="margin-top:14px">
        <h2>${t("ops.queues")}</h2><p class="muted small">${t("ops.queueHint")}</p>
        <table class="tbl"><thead><tr><th>${t("ops.queue")}</th><th>${t("ops.pending")}</th><th>${t("ops.overdue")}</th><th>${t("ops.oldest")}</th><th>${t("ops.failed")}</th></tr></thead>
          <tbody>${data.queues.map((q) => html`<tr key=${q.name}><td>${t("ops.queueNames." + q.name)}</td>
            <td>${q.states.pending || 0}</td><td><span class=${q.overdue ? "badge danger" : ""}>${q.overdue}</span></td>
            <td>${q.states.pending ? fmtSeconds(q.oldest_pending_seconds) : "—"}</td><td>${q.states.failed || 0}</td></tr>`)}</tbody></table>
      </div>
      <div class="card scroll-x" tabindex="0" role="region" aria-label=${t("ops.connections")} style="margin-top:14px">
        <h2>${t("ops.connections")}</h2>
        ${!connections.length ? html`<${Empty} label=${t("ops.noConnections")} />` : html`
          <table class="tbl"><thead><tr><th>${t("ops.channel")}</th><th>${t("ops.status")}</th><th>${t("ops.error")}</th></tr></thead>
            <tbody>${connections.map((c) => html`<tr key=${c.kind + c.channel}><td>${c.kind} · ${c.channel}</td>
              <td>${t(c.kind === "MQTT" && !c.attempted ? "ops.unused" : c.connected ? "ops.connected" : "ops.disconnected")}</td>
              <td>${c.error || "—"}</td></tr>`)}</tbody></table>`}
      </div>
      <div class="card scroll-x" tabindex="0" role="region" aria-label=${t("ops.failures")} style="margin-top:14px">
        <h2>${t("ops.failures")}</h2><p class="muted small">${t("ops.failureHint")}</p>
        ${!data.recent_failures.length ? html`<${Empty} label=${t("ops.noFailures")} />` : html`
          <table class="tbl"><thead><tr><th>${t("ops.queue")}</th><th>${t("ops.channel")}</th><th>${t("ops.attempts")}</th><th>${t("ops.error")}</th><th>${t("ops.created")}</th></tr></thead>
            <tbody>${data.recent_failures.map((f, i) => html`<tr key=${i}><td><a href=${"#/log?id=" + encodeURIComponent(f.notification_id)}>${t("ops.queueNames." + f.queue)}</a></td>
              <td>${f.channel}</td><td>${f.attempts}</td><td>${f.error || "—"}</td><td>${fmtDateTime(f.created_at)}</td></tr>`)}</tbody></table>`}
      </div>`}
  </div>`;
}
