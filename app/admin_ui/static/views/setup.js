// Setup guide (#/setup) and the dashboard's "Getting started" card.
//
// Four steps: welcome → where alerts go (a channel + a test send) → what to
// watch (a pack, your own scripts, or Prometheus) → done. Progress comes from
// GET /v1/setup/status, which derives every step from the live configuration,
// so the guide is right however things were set up (UI, API, a pack).
import { html, useEffect, useState, useCallback } from "../lib/h.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { ErrorState, Spinner } from "../lib/ui.js";
import { t, lt } from "../lib/i18n.js";
import { navigate } from "../lib/router.js";
import { ChannelEditor, KindPicker } from "./channels.js";
import { InstallDrawer } from "./packs.js";
import { PushCard } from "./push.js";

const BUILT_IN = new Set(["ui", "banner"]);
// Where each unfinished step is done, for the checklist links.
const STEP_LINK = { channel: "#/setup?step=1", channel_tested: "#/setup?step=1", source: "#/setup?step=2", rules: "#/setup?step=2", first_alert: "#/setup?step=2" };
const STEPS = ["welcome", "notify", "watch", "done"];

export function useSetupStatus() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const reload = useCallback(async () => {
    try { setStatus(await api.get("/v1/setup/status")); setError(null); } catch (e) { setError(e); }
  }, []);
  useEffect(() => { reload(); }, [reload]);
  return { status, error, reload };
}

function Checklist({ status }) {
  return html`<ul class="checklist">${status.steps.map((s) => html`<li key=${s.id} class=${s.done ? "done" : ""}>
    <span class="check" aria-hidden="true">${s.done ? "✓" : "○"}</span>
    <span>${s.done ? t(`setup.step.${s.id}`) : html`<a href=${STEP_LINK[s.id]}>${t(`setup.step.${s.id}`)}</a>`}
      <span class="sr-only">${s.done ? t("setup.doneSr") : t("setup.todoSr")}</span></span>
  </li>`)}</ul>`;
}

/** Dashboard card: shown until the setup is complete or hidden. */
export function SetupCard({ user }) {
  const { status, reload } = useSetupStatus();
  // Optional on the dashboard: a failed or unexpected status hides the card
  // instead of breaking the page around it.
  if (!status || !Array.isArray(status.steps) || status.complete || status.dismissed) return null;
  const done = status.steps.filter((s) => s.done).length;
  async function hide() {
    try { await api.post("/v1/setup/dismiss"); toast.info(t("setup.hidden")); reload(); } catch (e) { toast.error(e); }
  }
  return html`<section class="card setup-card" aria-labelledby="setup-card-h">
    <div class="setup-card-head">
      <h2 id="setup-card-h">${t("setup.cardTitle")}</h2>
      <span class="muted small">${t("setup.progress", { done, total: status.steps.length })}</span>
    </div>
    <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax=${status.steps.length} aria-valuenow=${done}
      aria-label=${t("setup.cardTitle")}><span style=${`width:${Math.round((100 * done) / status.steps.length)}%`}></span></div>
    <${Checklist} status=${status} />
    <div class="form-actions">
      <a class="btn primary" href="#/setup">${done ? t("setup.continue") : t("setup.start")}</a>
      ${user?.role === "admin" ? html`<button class="btn ghost" onClick=${hide}>${t("setup.hide")}</button>` : null}
    </div>
  </section>`;
}

export function SetupView({ query }) {
  const { status, error, reload } = useSetupStatus();
  const [step, setStep] = useState(() => Math.min(3, Math.max(0, Number(query?.step) || 0)));
  const [meta, setMeta] = useState(null);
  const [channels, setChannels] = useState(null);
  const [catalog, setCatalog] = useState([]);

  const loadChannels = useCallback(async () => {
    try { setChannels((await api.get("/v1/channels", { limit: 500 })).items); } catch (e) { toast.error(e); }
  }, []);
  useEffect(() => {
    loadChannels();
    api.get("/v1/meta/kinds").then(setMeta).catch((e) => toast.error(e));
    api.get("/v1/packs").then((r) => setCatalog(r.items)).catch(() => {});
  }, [loadChannels]);
  useEffect(() => { if (query?.step !== undefined) setStep(Math.min(3, Math.max(0, Number(query.step) || 0))); }, [query?.step]);

  const go = (n) => { setStep(n); reload(); window.scrollTo(0, 0); };
  if (error) return html`<${ErrorState} error=${error} onRetry=${reload} />`;
  if (!status || !channels) return html`<${Spinner} />`;
  const external = channels.filter((c) => !BUILT_IN.has(c.kind));

  return html`<div class="setup">
    <div class="page-head"><div><h1>${t("setup.title")}</h1><p class="muted">${t("setup.subtitle")}</p></div></div>
    <ol class="stepper">${STEPS.map((s, i) => html`<li key=${s} class=${i === step ? "current" : i < step ? "past" : ""}>
      <button type="button" class="link-btn" aria-current=${i === step ? "step" : undefined} onClick=${() => go(i)}>
        <span class="step-n" aria-hidden="true">${i + 1}</span> ${t(`setup.stepTitle.${s}`)}</button></li>`)}</ol>

    <section class="card setup-step" aria-labelledby="setup-step-h">
      ${step === 0 ? html`<${Welcome} status=${status} onNext=${() => go(1)} />` : null}
      ${step === 1 ? html`<${Notify} meta=${meta} external=${external} status=${status}
          onChanged=${() => { loadChannels(); reload(); }} onNext=${() => go(2)} />` : null}
      ${step === 2 ? html`<${Watch} catalog=${catalog} channels=${channels} external=${external}
          onChanged=${() => { loadChannels(); reload(); }} onNext=${() => go(3)} />` : null}
      ${step === 3 ? html`<${Done} status=${status} reload=${reload} />` : null}
    </section>
  </div>`;
}

function Welcome({ status, onNext }) {
  return html`
    <h2 id="setup-step-h">${t("setup.welcomeTitle")}</h2>
    <p>${t("setup.welcomeLead")}</p>
    <ol class="flow">
      <li><b>${t("setup.flowSources")}</b> — ${t("setup.flowSourcesText")}</li>
      <li><b>${t("setup.flowRules")}</b> — ${t("setup.flowRulesText")}</li>
      <li><b>${t("setup.flowTemplates")}</b> — ${t("setup.flowTemplatesText")}</li>
      <li><b>${t("setup.flowChannels")}</b> — ${t("setup.flowChannelsText")}</li>
    </ol>
    <p class="small">${t("setup.timezone", { tz: status.timezone })}
      ${status.timezone === "UTC" ? html` <span class="muted">${t("setup.timezoneHint")}</span>` : null}</p>
    <p class="small muted">${t("setup.prefsHint")}</p>
    <div class="form-actions"><button class="btn primary" onClick=${onNext}>${t("setup.start")}</button></div>`;
}

function Notify({ meta, external, onChanged, onNext }) {
  const [creating, setCreating] = useState(null);    // kind
  const [results, setResults] = useState({});        // channel id → test result
  const [testing, setTesting] = useState(null);

  async function test(ch) {
    setTesting(ch.id);
    try {
      const r = await api.post(`/v1/channels/${ch.id}/test`);
      setResults((cur) => ({ ...cur, [ch.id]: r }));
      onChanged();
    } catch (e) { toast.error(e); } finally { setTesting(null); }
  }

  return html`
    <h2 id="setup-step-h">${t("setup.notifyTitle")}</h2>
    <p>${t("setup.notifyLead")}</p>
    ${external.length ? html`<ul class="setup-channels">${external.map((c) => {
      const r = results[c.id];
      return html`<li key=${c.id}>
        <b>${c.name}</b> <span class="muted small mono">${c.kind}</span>
        <button class="btn sm" disabled=${testing === c.id} onClick=${() => test(c)}>${testing === c.id ? t("setup.testing") : t("setup.sendTest")}</button>
        ${r ? (r.ok ? html`<span class="badge ok plain" role="status">${t("setup.testOk")}</span>`
          : html`<span class="badge critical plain" role="status">${t("setup.testFailed")}</span> <span class="small error">${r.error || ""}</span>`) : null}
      </li>`;
    })}</ul>
    <p class="small muted">${t("setup.testHint")}</p>
    <h3>${t("setup.addAnother")}</h3>` : null}
    ${meta ? html`<${KindPicker} kinds=${Object.keys(meta.channels || {})} exclude=${["ui", "banner"]} onPick=${setCreating} />` : html`<${Spinner} />`}
    <div class="setup-phone">
      <h3>${t("setup.phoneTitle")}</h3>
      ${external.some((c) => c.kind === "push" && c.enabled)
        ? html`<${PushCard} admin=${true} />`
        : html`<p class="small">${t("setup.phoneHow")}</p>`}
    </div>
    <div class="form-actions">
      <button class="btn primary" onClick=${onNext}>${external.length ? t("setup.next") : t("setup.skipNotify")}</button>
    </div>
    ${creating ? html`<${ChannelEditor} channel=${{ __new: true }} meta=${meta} initialKind=${creating}
        onClose=${() => setCreating(null)}
        onSaved=${(saved) => { setCreating(null); onChanged(); if (saved?.id) test(saved); }} />` : null}`;
}

function Watch({ catalog, channels, external, onChanged, onNext }) {
  const [installing, setInstalling] = useState(null);
  const [script, setScript] = useState(null);       // {key, sent}
  const [busy, setBusy] = useState(false);
  const target = external[0]?.name || "ui_default";
  const pack = (id) => catalog.find((p) => p.id === id);
  const channelNames = channels.map((c) => c.name).sort();

  async function setupScripts() {
    setBusy(true);
    try {
      const applied = await api.post("/v1/packs/apply", { pack_id: "script-alerts", params: { alert_channel: target } });
      if (!applied.applied) { toast.error((applied.errors || []).join("; ") || t("transfer.notApplied")); return; }
      const key = await api.post("/v1/api_keys", { name: `scripts-${Date.now().toString(36)}`, scopes: ["fire"] });
      setScript({ key: key.key, sent: null });
      onChanged();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }
  async function sendFirst() {
    try {
      const r = await api.post("/v1/fire", { type: "script_info", context: { title: t("setup.firstAlertTitle"), message: t("setup.firstAlertMessage") } });
      setScript((s) => ({ ...s, sent: r }));
      onChanged();
    } catch (e) { toast.error(e); }
  }
  const curl = script ? `curl -X POST ${location.origin}/v1/fire \\\n  -H "X-API-Key: ${script.key}" -H "Content-Type: application/json" \\\n  -d '{"type": "script_warning", "context": {"title": "Backup is late", "message": "Last run 26h ago"}}'` : "";

  return html`
    <h2 id="setup-step-h">${t("setup.watchTitle")}</h2>
    <p>${t("setup.watchLead", { channel: target })}</p>
    <div class="cards watch-options">
      <article class="card">
        <h3>${t("setup.optScripts")}</h3>
        <p class="small">${t("setup.optScriptsText")}</p>
        ${script ? html`<div class="key-once" role="status">
            <p class="small"><b>${t("setup.keyOnce")}</b></p>
            <pre class="json" tabindex="0">${curl}</pre>
            <div class="form-actions">
              <button class="btn sm" onClick=${() => navigator.clipboard?.writeText(curl).then(() => toast.ok(t("setup.copied")))}>${t("setup.copy")}</button>
              <button class="btn primary sm" onClick=${sendFirst}>${t("setup.sendFirst")}</button>
            </div>
            ${script.sent ? html`<p class="small">${script.sent.dispatched ? t("setup.firstSent", { channels: script.sent.channels.join(", ") }) : t("setup.firstNotSent", { reason: script.sent.suppressed_reason || script.sent.status })}</p>` : null}
          </div>`
          : html`<button class="btn primary sm" disabled=${busy} onClick=${setupScripts}>${t("setup.optScriptsBtn")}</button>`}
      </article>
      <article class="card">
        <h3>${t("setup.optDevices")}</h3>
        <p class="small">${t("setup.optDevicesText")}</p>
        <div class="form-actions">${["sensor-threshold", "service-heartbeat"].filter(pack).map((id) => html`<button key=${id} class="btn sm"
            onClick=${() => setInstalling(pack(id))}>${lt(pack(id).name)}</button>`)}</div>
      </article>
      <article class="card">
        <h3>${t("setup.optPrometheus")}</h3>
        <p class="small">${t("setup.optPrometheusText")}</p>
        ${pack("alertmanager") ? html`<button class="btn sm" onClick=${() => setInstalling(pack("alertmanager"))}>${lt(pack("alertmanager").name)}</button>` : null}
      </article>
    </div>
    <p class="small"><a href="#/packs">${t("setup.allPacks")}</a></p>
    <div class="form-actions"><button class="btn primary" onClick=${onNext}>${t("setup.next")}</button></div>
    ${installing ? html`<${InstallDrawer} source=${{ pack_id: installing.id }}
        summary=${{ ...installing, parameters: installing.parameters.map((p) => (p.type === "channel" ? { ...p, default: target } : p)) }}
        channels=${channelNames} onClose=${() => setInstalling(null)}
        onDone=${() => { setInstalling(null); onChanged(); }} />` : null}`;
}

function Done({ status, reload }) {
  async function hide() {
    try { await api.post("/v1/setup/dismiss"); reload(); navigate("/dashboard"); } catch (e) { toast.error(e); }
  }
  async function reopen() {
    try { await api.post("/v1/setup/reopen"); reload(); toast.ok(t("setup.reopened")); } catch (e) { toast.error(e); }
  }
  return html`
    <h2 id="setup-step-h">${status.complete ? t("setup.doneTitle") : t("setup.almostTitle")}</h2>
    <p>${status.complete ? t("setup.doneLead") : t("setup.almostLead")}</p>
    <${Checklist} status=${status} />
    <h3>${t("setup.nextTitle")}</h3>
    <ul class="flow">
      <li><a href="#/rules">${t("setup.nextRules")}</a></li>
      <li><a href="#/templates">${t("setup.nextTemplates")}</a></li>
      <li><a href="#/api">${t("setup.nextApi")}</a></li>
    </ul>
    <div class="form-actions">
      <a class="btn primary" href="#/dashboard">${t("setup.toDashboard")}</a>
      ${!status.dismissed ? html`<button class="btn ghost" onClick=${hide}>${t("setup.hideGuide")}</button>`
        : html`<button class="btn ghost" onClick=${reopen}>${t("setup.reopen")}</button>`}
    </div>`;
}
