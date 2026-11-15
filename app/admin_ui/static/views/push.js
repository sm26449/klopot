// "Notifications on this device" (docs/WEB_PUSH.md): enable Web Push on this
// browser / installed app, and the list of every device that receives it.
import { html, useEffect, useState } from "../lib/h.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { ErrorState, Spinner } from "../lib/ui.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import { sevLabel } from "../lib/labels.js";
import { t } from "../lib/i18n.js";
import { browserEnv, currentSubscription, enablePush, endpointHash, pushState, unsubscribeHere } from "../lib/push.js";

const SEVERITIES = ["info", "warning", "critical"];

export function PushCard({ admin }) {
  const [config, setConfig] = useState(null);
  const [devices, setDevices] = useState(null);
  const [error, setError] = useState(null);
  const [here, setHere] = useState(null);       // this browser's endpoint hash, if subscribed
  const [busy, setBusy] = useState(false);
  const state = pushState(browserEnv());

  async function load() {
    setError(null);
    try {
      const [c, d] = await Promise.all([api.get("/v1/push/config"), api.get("/v1/push/subscriptions")]);
      setConfig(c); setDevices(d);
      const sub = state === "ready" ? await currentSubscription().catch(() => null) : null;
      setHere(sub ? await endpointHash(sub.endpoint) : null);
    } catch (e) { setError(e); }
  }
  useEffect(() => { load(); }, []);

  const mine = devices && here ? devices.find((d) => d.endpoint_hash === here) : null;

  async function enable() {
    setBusy(true);
    try {
      await enablePush(config.public_key);
      toast.ok(t("push.toastEnabled"));
      await load();
    } catch (e) {
      if (e.code === "denied") toast.error(t("push.deniedNow"));
      else if (e.code === "dismissed") toast.info(t("push.dismissed"));
      else toast.error(e);
      await load();
    } finally { setBusy(false); }
  }
  async function test(d) {
    setBusy(true);
    try {
      const r = await api.post(`/v1/push/subscriptions/${d.id}/test`);
      if (r.ok) toast.ok(t("push.toastTestSent", { label: d.label })); else toast.error(r.error || t("push.testFailed"));
      await load();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }
  async function patch(d, body) {
    try { await api.patch(`/v1/push/subscriptions/${d.id}`, body); await load(); } catch (e) { toast.error(e); }
  }
  async function rename(d) {
    const label = prompt(t("push.renamePrompt"), d.label);
    if (label && label.trim() && label.trim() !== d.label) await patch(d, { label: label.trim() });
  }
  async function remove(d) {
    if (!confirm(t("push.confirmRemove", { label: d.label }))) return;
    setBusy(true);
    try {
      if (mine && d.id === mine.id) await unsubscribeHere().catch(() => {});
      await api.del(`/v1/push/subscriptions/${d.id}`);
      toast.ok(t("push.toastRemoved"));
      await load();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  return html`<div class="card push-card">
    <h2>${t("push.title")}</h2>
    ${error ? html`<${ErrorState} error=${error} onRetry=${load} />` : config === null ? html`<${Spinner} />` : html`
      <${ThisDevice} state=${state} config=${config} mine=${mine} busy=${busy} admin=${admin}
        onEnable=${enable} onTest=${() => test(mine)} onRemove=${() => remove(mine)} />
      ${devices.length ? html`<${DeviceList} devices=${devices} mine=${mine} admin=${admin} busy=${busy}
        onTest=${test} onPatch=${patch} onRename=${rename} onRemove=${remove} />` : null}`}
  </div>`;
}

function ThisDevice({ state, config, mine, busy, admin, onEnable, onTest, onRemove }) {
  if (!config.enabled && config.channel) {
    return html`<p class="err">${t("push.channelBroken", { channel: config.channel, reason: config.reason || "?" })}</p>
      ${admin ? html`<p class="small"><a href="#/channels">${t("push.fixChannel")}</a></p>` : null}`;
  }
  if (!config.enabled) {
    return html`<p class="muted">${t("push.noChannel")}${admin ? html` <a href="#/channels">${t("push.addChannel")}</a>` : null}</p>
      <p class="muted small">${t("push.noChannelHelp")}</p>`;
  }
  if (state === "insecure") return html`<p class="muted">${t("push.insecure")}</p>`;
  if (state === "unsupported") return html`<p class="muted">${t("push.unsupported")}</p>`;
  if (state === "ios-install") {
    return html`<div class="push-install">
      <img src="icons/apple-touch-icon.png" alt="" width="48" height="48" />
      <div><p><b>${t("push.iosTitle")}</b></p>
        <ol class="small"><li>${t("push.iosStep1")}</li><li>${t("push.iosStep2")}</li><li>${t("push.iosStep3")}</li></ol>
        <p class="muted small">${t("push.iosNote")}</p></div>
    </div>`;
  }
  if (state === "denied") return html`<p class="muted">${t("push.denied")}</p>`;
  if (mine) {
    return html`<p><span class="badge ok plain">${t("push.onHere")}</span> ${t("push.onHereText", { label: mine.label, sev: t("push.fromSeverity", { sev: sevLabel(mine.min_severity) }) })}</p>
      <div class="actions-row">
        <button class="btn sm" onClick=${onTest} disabled=${busy || !admin}>${t("push.sendTest")}</button>
        ${admin ? html`<button class="btn sm danger" onClick=${onRemove} disabled=${busy}>${t("push.turnOff")}</button>` : null}
      </div>`;
  }
  return html`<p class="muted">${t("push.intro")}</p>
    <button class="btn primary" onClick=${onEnable} disabled=${busy}>${t("push.enable")}</button>`;
}

function DeviceList({ devices, mine, admin, busy, onTest, onPatch, onRename, onRemove }) {
  return html`<h3 class="push-devices-title">${t("push.devices")}</h3>
    <div class="scroll-x" tabindex="0"><table class="tbl push-devices">
      <thead><tr><th>${t("push.colDevice")}</th><th>${t("push.colMinSeverity")}</th><th>${t("push.colOn")}</th>
        <th>${t("push.colLast")}</th><th><span class="sr-only">${t("common.actions")}</span></th></tr></thead>
      <tbody>${devices.map((d) => html`<tr key=${d.id} class=${d.enabled ? "" : "muted"}>
        <td>${admin ? html`<button type="button" class="link-btn" onClick=${() => onRename(d)}
              aria-description=${t("push.rename")}>${d.label}</button>` : d.label}
          ${mine && d.id === mine.id ? html` <span class="chip">${t("push.thisDevice")}</span>` : null}
          <div class="muted small mono">${d.service}</div></td>
        <td>${admin ? html`<select aria-label=${t("push.minSeverityFor", { label: d.label })} value=${d.min_severity}
              onChange=${(e) => onPatch(d, { min_severity: e.target.value })}>
              ${SEVERITIES.map((s) => html`<option key=${s} value=${s}>${t("push.fromSeverity", { sev: sevLabel(s) })}</option>`)}</select>`
            : t("push.fromSeverity", { sev: sevLabel(d.min_severity) })}</td>
        <td><input type="checkbox" checked=${d.enabled} disabled=${!admin}
              aria-label=${t("push.enabledFor", { label: d.label })} onChange=${(e) => onPatch(d, { enabled: e.target.checked })} />
          ${!d.enabled && d.paused_reason === "service" ? html`<div class="err small">${t("push.pausedByService")}</div>` : null}</td>
        <td class="small">${d.last_success_at ? html`<span title=${fmtDateTime(d.last_success_at)}>${t("push.delivered", { when: fmtRelative(d.last_success_at) })}</span>`
            : html`<span class="muted">${t("push.never")}</span>`}
          ${d.last_error ? html`<div class="err small" title=${d.last_error}>${t("push.lastError", { n: d.consecutive_failures })}</div>` : null}</td>
        <td class="nowrap">${admin ? html`<button class="btn sm" onClick=${() => onTest(d)} disabled=${busy}>${t("push.test")}</button>
            <button class="btn sm danger" onClick=${() => onRemove(d)} disabled=${busy}
              aria-label=${t("push.removeFor", { label: d.label })}>${t("push.remove")}</button>` : null}</td>
      </tr>`)}</tbody>
    </table></div>`;
}
