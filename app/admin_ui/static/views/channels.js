// Channels (phase F5): cards + a typed editor generated from
// /v1/meta/kinds, webhook presets, write-only secret fields, and the
// test / health / breaker-reset / delete actions.
import { html, useState, useEffect, useCallback } from "../lib/h.js";
import { useGuard } from "../lib/action.js";
import { clickable } from "../lib/a11y.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { Drawer, useDirty, Spinner, Empty, ErrorState, StaleBanner, Json, DangerConfirm, ConfirmModal, ListMeta, KindHelp, DraftBanner } from "../lib/ui.js";
import { useDraft } from "../lib/draft.js";
import { FieldInput, useFieldErrors, FieldErrorSummary, FieldMsg, SecretField, applySecretEdits, configDefaults, useFieldValidity, fieldVisible, visibleConfig } from "../lib/form.js";
import { t, tnode } from "../lib/i18n.js";
import { ChannelActivity } from "./activity.js";

const KIND_ICON = { ui: "🖥️", banner: "📢", telegram: "✈️", sms: "📱", email: "✉️", push: "🔔", webhook: "🔗",
  ntfy: "📣", gotify: "📬", pushover: "📲", mqtt: "📡" };
// Product names — the same in every language.
const KIND_LABEL = { ui: "Admin UI", banner: "Banner", telegram: "Telegram", sms: "SMS", email: "Email", push: "Web Push",
  webhook: "Webhook", ntfy: "ntfy", gotify: "Gotify", pushover: "Pushover", mqtt: "MQTT" };
// Order in the picker: personal notifications first, integrations next, the
// built-in UI destinations last (every install already has them).
const KIND_ORDER = ["telegram", "ntfy", "email", "pushover", "gotify", "sms", "push", "webhook", "mqtt", "ui", "banner"];

/** Channel kinds as cards (icon, name, one line on what it is for). */
export function KindPicker({ kinds, onPick, exclude = [] }) {
  const rank = (k) => { const i = KIND_ORDER.indexOf(k); return i < 0 ? KIND_ORDER.length : i; };
  const list = kinds.filter((k) => !exclude.includes(k)).sort((a, b) => rank(a) - rank(b));
  return html`<ul class="kind-picker">${list.map((k) => {
    const lead = t(`channels.help.${k}.lead`);
    return html`<li key=${k}><button type="button" class="kind-card" onClick=${() => onPick(k)}>
      <span class="kind-icon" aria-hidden="true">${KIND_ICON[k] || "📨"}</span>
      <span class="kind-text"><b>${KIND_LABEL[k] || k}</b>
        ${lead !== `channels.help.${k}.lead` ? html`<span class="small muted">${lead}</span>` : null}</span>
    </button></li>`;
  })}</ul>`;
}

export function ChannelsView() {
  const [channels, setChannels] = useState(null);
  const [total, setTotal] = useState(null);
  const [usage, setUsage] = useState({});       // id → count
  const [meta, setMeta] = useState(null);
  const [editing, setEditing] = useState(null); // channel obj | {__new:true}
  const [err, setErr] = useState(null); // persistent list-load error (UX-006)

  const load = useCallback(async () => {
    setErr(null);
    try {
      const p = await api.get("/v1/channels", { limit: 500 });
      setChannels(p.items);
      setTotal(p.total);
      // routes count per channel (few channels — parallel is fine)
      const counts = {};
      await Promise.all(p.items.map(async (c) => {
        try { counts[c.id] = (await api.get(`/v1/channels/${c.id}/usage`)).templates.length; } catch { counts[c.id] = 0; }
      }));
      setUsage(counts);
    } catch (e) { setErr(e); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/v1/meta/kinds").then(setMeta).catch((e) => toast.error(e)); }, []);

  return html`<div>
    <div class="page-head">
      <div><h1>${t("channels.title")}</h1><p class="muted">${t("channels.subtitle")}</p></div>
      <div class="actions"><button class="btn primary" onClick=${() => setEditing({ __new: true })}>${t("channels.newChannel")}</button></div>
    </div>

    <${ListMeta} total=${total} limit=${500} />
    ${err && channels ? html`<${StaleBanner} error=${err} onRetry=${load} />` : null}
    ${err && channels === null ? html`<${ErrorState} error=${err} onRetry=${load} />` : channels === null ? html`<${Spinner} />` : channels.length === 0
      ? html`<${Empty} title=${t("channels.blank.title")} body=${t("channels.blank.body")}
          actions=${[{ label: t("channels.newChannel"), primary: true, onClick: () => setEditing({ __new: true }) }, { label: t("common.openGuide"), href: "#/setup" }]} />`
      : html`<div class="cards">${channels.map((c) => html`<div key=${c.id} class="ch-card" ...${clickable(() => setEditing(c), t("channels.editAria", { name: c.name }))}>
          <div class="ch-top"><span class="ch-icon">${KIND_ICON[c.kind] || "📨"}</span>
            <b>${c.name}</b><span class="spacer"></span>
            <span class="badge ${c.enabled ? "ok" : ""} plain">${c.enabled ? t("channels.enabled") : t("channels.disabled")}</span></div>
          <div class="ch-meta small muted">
            <span class="mono">${c.kind}</span> · ${c.rate_limit_per_min}${t("channels.perMin")} · ${usage[c.id] ?? "…"} ${t("channels.routes")}
          </div>
          ${Object.keys(c.secret_fields_set || {}).length
            ? html`<div class="small muted">🔒 ${Object.keys(c.secret_fields_set).join(", ")}</div>` : null}
        </div>`)}</div>`}

    ${editing ? html`<${ChannelEditor} channel=${editing} meta=${meta}
        onClose=${() => setEditing(null)} onSaved=${() => { setEditing(null); load(); }} />` : null}
  </div>`;
}

function blankConfigFor(meta, kind) {
  return configDefaults(meta?.channels?.[kind]?.fields);
}

// `initialKind` opens a new channel with that kind already chosen (the setup
// guide); `onSaved(saved)` receives the channel as the API returned it.
export function ChannelEditor({ channel, meta, onClose, onSaved, initialKind = "" }) {
  const isNew = !!channel.__new;
  const [kind, setKind] = useState(isNew ? initialKind : channel.kind);
  const [name, setName] = useState(isNew ? (initialKind ? `${initialKind}_main` : "") : channel.name);
  const [config, setConfig] = useState(isNew ? (initialKind ? blankConfigFor(meta, initialKind) : {}) : { ...(channel.config || {}) });
  const [enabled, setEnabled] = useState(isNew ? true : channel.enabled);
  const [rate, setRate] = useState(isNew ? 30 : channel.rate_limit_per_min);
  const [secretEdits, setSecretEdits] = useState({});
  const [busy, setBusy] = useState(false);
  const fieldErrs = useFieldErrors();
  const [acting, guard] = useGuard();
  const [health, setHealth] = useState(null);
  const validity = useFieldValidity();
  const [testResult, setTestResult] = useState(null);
  const [confirmDel, setConfirmDel] = useState(false);
  const [delWarn, setDelWarn] = useState(null);
  const [confirmReset, setConfirmReset] = useState(false);

  const fields = meta?.channels?.[kind]?.fields || [];
  const presets = meta?.webhook_presets || [];

  function setField(n, v) { setConfig((c) => ({ ...c, [n]: v })); }
  function applyPreset(id) {
    const p = presets.find((x) => x.id === id);
    if (p) { setConfig((c) => ({ ...c, ...p.config })); toast.info(t("channels.presetApplied", { label: p.label, help: p.help })); }
  }
  function chooseKind(k) {
    setKind(k); setConfig(blankConfigFor(meta, k)); setSecretEdits({}); validity.reset();
    if (isNew && (!name || /^[a-z]+_main$/.test(name))) setName(`${k}_main`);
  }

  async function save() {
    fieldErrs.clear();
    if (!fieldErrs.check([
      ["kind", !isNew || kind, t("channels.pickKind")],
      ["name", !isNew || /^[a-z][a-z0-9_-]*$/.test(name), name ? t("channels.nameRule") : null],
    ])) return;
    if (validity.anyInvalid) { validity.focusFirst(); return toast.error(t("channels.fixJson")); }
    setBusy(true);
    try {
      const outConfig = applySecretEdits(visibleConfig(config, fields), fields, secretEdits);
      let saved;
      if (isNew) {
        saved = await api.post("/v1/channels", { name, kind, config: outConfig, enabled, rate_limit_per_min: Number(rate) });
        toast.ok(t("channels.created"));
      } else {
        saved = await api.patch(`/v1/channels/${channel.id}`, { config: outConfig, enabled, rate_limit_per_min: Number(rate) });
        toast.ok(t("channels.saved"));
      }
      draft.clear();
      onSaved(saved);
    } catch (e) { if (!fieldErrs.show(e)) toast.error(e); } finally { setBusy(false); }
  }

  // Guarded so a fast double-click can't fire a second test send (UX-016).
  function doTest() {
    return guard(async () => {
      setTestResult(null);
      try { setTestResult(await api.post(`/v1/channels/${channel.id}/test`)); }
      catch (e) { toast.error(e); }
    });
  }
  async function doHealth() {
    setHealth(null);
    try { setHealth(await api.get(`/v1/channels/${channel.id}/health`)); }
    catch (e) { toast.error(e); }
  }
  function resetBreaker() {
    return guard(async () => {
      try { const r = await api.post(`/v1/channels/${channel.id}/breaker/reset`); toast.ok(t("channels.breakerState", { state: r.state })); doHealth(); }
      catch (e) { toast.error(e); }
    });
  }
  async function askDelete() {
    try { const u = await api.get(`/v1/channels/${channel.id}/usage`);
      setDelWarn(u.templates.length ? t("channels.delWarnTemplates", { count: u.templates.length, types: u.templates.map((t) => t.type).join(", ") }) : null);
    } catch { setDelWarn(null); }
    setConfirmDel(true);
  }
  async function doDelete() {
    setBusy(true);
    try { await api.del(`/v1/channels/${channel.id}`); toast.ok(t("channels.deleted")); draft.clear(); onSaved(); }
    catch (e) { toast.error(e); setConfirmDel(false); } finally { setBusy(false); }
  }

  const dirty = useDirty({ kind, name, config, enabled, rate, secretEdits }) || validity.anyInvalid;
  // Draft recovery (UX-007). Secret edits are deliberately left OUT of the
  // persisted draft — a freshly typed token must not land in sessionStorage; it
  // is re-entered after a restore.
  const draft = useDraft("channels", isNew ? null : channel.id, { kind, name, config, enabled, rate }, dirty);
  const restoreDraft = () => { const d = draft.recovered; setKind(d.kind); setName(d.name); setConfig(d.config); setEnabled(d.enabled); setRate(d.rate); draft.restore(); };
  const closeDraft = () => { draft.clear(); onClose(); };
  return html`<${Drawer} open=${true} width=${640} title=${isNew ? t("channels.newChannel") : channel.name} onClose=${closeDraft} dirty=${dirty}>
      ${draft.recovered ? html`<${DraftBanner} onRestore=${restoreDraft} onDiscard=${draft.dismiss} />` : null}
      <${FieldErrorSummary} errors=${fieldErrs.errors}
        idFor=${(f) => ({ name: "ch-name", kind: "ch-kind" }[f.split(".").pop()] || "f_" + f.split(".").pop())} />
    <div class="editor">
      ${isNew && !kind ? html`<p class="muted">${t("channels.pickKindLead")}</p>
        <${KindPicker} kinds=${Object.keys(meta?.channels || {})} onPick=${chooseKind} />` : null}
      ${isNew && kind ? html`<div class="row2">
        <div class="field"><label for="ch-name">${t("channels.nameLabel")} <span class="req">*</span></label>
          <input id="ch-name" value=${name} onInput=${(e) => setName(e.target.value)} placeholder=${t("channels.namePlaceholder")} ...${fieldErrs.attrs("name")} />
          <${FieldMsg} fe=${fieldErrs} name="name" /></div>
        <div class="field"><label for="ch-kind">${t("channels.kindLabel")} <span class="req">*</span></label>
          <select id="ch-kind" value=${kind} onChange=${(e) => chooseKind(e.target.value)} ...${fieldErrs.attrs("kind")}>
            ${Object.keys(meta?.channels || {}).map((k) => html`<option key=${k} value=${k}>${KIND_LABEL[k] || k}</option>`)}
          </select></div>
      </div>` : null}
      ${!isNew ? html`<p class="muted small mono">${channel.kind} · id ${channel.id}</p>` : null}

      ${kind === "webhook" ? html`<div class="field"><label for="ch-preset">${t("channels.presetLabel")}</label>
        <select id="ch-preset" onChange=${(e) => e.target.value && applyPreset(e.target.value)}>
          <option value="">${t("channels.choosePreset")}</option>
          ${presets.map((p) => html`<option key=${p.id} value=${p.id}>${p.label}</option>`)}
        </select></div>` : null}

      ${kind ? fields.filter((f) => fieldVisible(f, config, fields)).map((f) => f.secret
        ? html`<${SecretField} key=${f.name} field=${f}
            status=${(channel.secret_fields_set || {})[f.name]}
            onChange=${(u) => setSecretEdits((s) => ({ ...s, [f.name]: u }))} />`
        : html`<${FieldInput} key=${f.name} field=${f} value=${config[f.name]} onInput=${(v) => setField(f.name, v)}
            error=${fieldErrs.msgFor(f.name)} onValidity=${(ok) => validity.setValidity(f.name, ok)} />`)
        : null}

      ${kind ? html`<div class="row2">
        <div class="field"><label for="ch-rate">${t("channels.rateLabel")}</label>
          <input id="ch-rate" type="number" value=${rate} onInput=${(e) => setRate(e.target.value)} /></div>
        <div class="field"><label class="chk"><input type="checkbox" checked=${enabled}
          onChange=${(e) => setEnabled(e.target.checked)} /> ${t("channels.enabledLabel")}</label></div>
      </div>` : null}

      ${kind ? html`<div class="editor-actions">
        <button class="btn primary" onClick=${save} disabled=${busy || !kind || validity.anyInvalid}>${isNew ? t("channels.create") : t("channels.save")}</button>
        ${!isNew ? html`
          <button class="btn" onClick=${doTest} disabled=${busy || acting}>${t("channels.test")}</button>
          <button class="btn" onClick=${doHealth} disabled=${busy}>${t("channels.healthBtn")}</button>
          <button class="btn" onClick=${() => setConfirmReset(true)} disabled=${busy || acting}>${t("channels.resetBreaker")}</button>
          <span class="spacer"></span>
          <button class="btn danger" onClick=${askDelete} disabled=${busy}>${t("channels.delete")}</button>` : null}
      </div>` : null}

      ${testResult ? html`<div class="result"><b>${t("channels.testResultLabel")}</b> ${testResult.ok ? html`<span class="badge ok plain">${t("channels.okStatus")}</span>` : html`<span class="badge critical plain">${t("channels.failedStatus")}</span>`}
        ${testResult.error ? html`<div class="error small">${testResult.error}</div>` : null}
        ${testResult.response ? html`<${Json} value=${testResult.response} />` : null}</div>` : null}
      ${health ? html`<div class="result"><b>${t("channels.healthResultLabel")}</b> <${Json} value=${health} /></div>` : null}

      ${!isNew ? html`<${ChannelActivity} name=${channel.name} refresh=${testResult} />` : null}
      <${KindHelp} help=${tnode(kind ? "channels.help." + kind : "channels.help.intro")} />
    </div>

    <${DangerConfirm} open=${confirmDel} token=${channel.name} title=${t("channels.deleteTitle", { name: channel.name })}
      warning=${delWarn} busy=${busy} onConfirm=${doDelete} onClose=${() => setConfirmDel(false)} />
    <${ConfirmModal} open=${confirmReset} title=${t("channels.resetBreakerConfirmTitle")}
      message=${t("channels.resetBreakerConfirmBody")} confirmLabel=${t("channels.resetBreaker")}
      onConfirm=${() => { setConfirmReset(false); resetBreaker(); }} onClose=${() => setConfirmReset(false)} />
  </${Drawer}>`;
}
