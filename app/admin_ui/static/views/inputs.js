// Inputs (phase F6): list with health + a typed editor from
// /v1/meta/kinds (secret fields), restart and enable/disable.
import { html, useState, useEffect, useCallback } from "../lib/h.js";
import { useGuard } from "../lib/action.js";
import { clickable } from "../lib/a11y.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { Drawer, useDirty, Spinner, Empty, ErrorState, StaleBanner, Json, DangerConfirm, ConfirmModal, ListMeta, KindHelp, DraftBanner } from "../lib/ui.js";
import { useDraft } from "../lib/draft.js";
import { FieldInput, useFieldErrors, FieldErrorSummary, SecretField, applySecretEdits, configDefaults, useFieldValidity } from "../lib/form.js";
import { t, tnode } from "../lib/i18n.js";

export function InputsView() {
  const [items, setItems] = useState(null);
  const [total, setTotal] = useState(null);
  const [meta, setMeta] = useState(null);
  const [editing, setEditing] = useState(null);
  const [err, setErr] = useState(null); // persistent list-load error (UX-006)

  const load = useCallback(async () => {
    setErr(null);
    try { const p = await api.get("/v1/inputs", { limit: 500 }); setItems(p.items); setTotal(p.total); }
    catch (e) { setErr(e); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/v1/meta/kinds").then(setMeta).catch(() => {}); }, []);

  return html`<div>
    <div class="page-head">
      <div><h1>${t("inputs.title")}</h1><p class="muted">${t("inputs.intro")}</p></div>
      <div class="actions"><button class="btn primary" onClick=${() => setEditing({ __new: true })}>${t("inputs.newInput")}</button></div>
    </div>

    <${ListMeta} total=${total} limit=${500} />
    ${err && items ? html`<${StaleBanner} error=${err} onRetry=${load} />` : null}
    ${err && items === null ? html`<${ErrorState} error=${err} onRetry=${load} />` : items === null ? html`<${Spinner} />` : items.length === 0 ? html`<${Empty} label=${t("inputs.empty")} />`
      : html`<div class="cards">${items.map((i) => html`<div key=${i.id} class="ch-card" ...${clickable(() => setEditing(i), t("inputs.editAria", { name: i.name }))}>
          <div class="ch-top"><b>${i.name}</b><span class="spacer"></span>
            <span class="badge ${i.enabled ? "ok" : ""} plain">${i.enabled ? t("inputs.badgeEnabled") : t("inputs.badgeDisabled")}</span></div>
          <div class="small muted"><span class="mono">${i.kind}</span></div>
          ${Object.keys(i.secret_fields_set || {}).length ? html`<div class="small muted">🔒 ${Object.keys(i.secret_fields_set).join(", ")}</div>` : null}
        </div>`)}</div>`}

    ${editing ? html`<${InputEditor} input=${editing} meta=${meta}
        onClose=${() => setEditing(null)} onSaved=${() => { setEditing(null); load(); }} />` : null}
  </div>`;
}

function InputEditor({ input, meta, onClose, onSaved }) {
  const isNew = !!input.__new;
  const [kind, setKind] = useState(isNew ? "" : input.kind);
  const [name, setName] = useState(isNew ? "" : input.name);
  const [config, setConfig] = useState(isNew ? {} : { ...(input.config || {}) });
  const [enabled, setEnabled] = useState(isNew ? true : input.enabled);
  const [secretEdits, setSecretEdits] = useState({});
  const [busy, setBusy] = useState(false);
  const fieldErrs = useFieldErrors();
  const [acting, guard] = useGuard();
  const [health, setHealth] = useState(null);
  const [confirmDel, setConfirmDel] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);

  const validity = useFieldValidity();
  const fields = meta?.inputs?.[kind]?.fields || [];
  function setField(n, v) { setConfig((c) => ({ ...c, [n]: v })); }
  function chooseKind(k) { setKind(k); setConfig(configDefaults(meta?.inputs?.[k]?.fields)); setSecretEdits({}); validity.reset(); }

  async function save() {
    fieldErrs.clear();
    if (isNew && !/^[a-z][a-z0-9_-]*$/.test(name)) return toast.error(t("inputs.nameRule"));
    if (isNew && !kind) return toast.error(t("inputs.pickKind"));
    if (validity.anyInvalid) { validity.focusFirst(); return toast.error(t("inputs.fixJson")); }
    setBusy(true);
    try {
      const outConfig = applySecretEdits(config, fields, secretEdits);
      if (isNew) { await api.post("/v1/inputs", { name, kind, config: outConfig, enabled }); toast.ok(t("inputs.created")); }
      else { await api.patch(`/v1/inputs/${input.id}`, { config: outConfig, enabled }); toast.ok(t("inputs.saved")); }
      draft.clear();
      onSaved();
    } catch (e) { if (!fieldErrs.show(e)) toast.error(e); } finally { setBusy(false); }
  }
  async function doHealth() {
    setHealth(null);
    try { setHealth(await api.get(`/v1/inputs/${input.id}/health`)); } catch (e) { toast.error(e); }
  }
  // Guarded so a double-click can't queue two restarts (UX-016).
  function restart() {
    return guard(async () => {
      try { await api.post(`/v1/inputs/${input.id}/restart`); toast.ok(t("inputs.restarted")); setTimeout(doHealth, 500); }
      catch (e) { toast.error(e); }
    });
  }
  async function doDelete() {
    setBusy(true);
    try { await api.del(`/v1/inputs/${input.id}`); toast.ok(t("inputs.deleted")); draft.clear(); onSaved(); }
    catch (e) { toast.error(e); setConfirmDel(false); } finally { setBusy(false); }
  }

  const dirty = useDirty({ kind, name, config, enabled, secretEdits }) || validity.anyInvalid;
  // Draft recovery (UX-007). secretEdits is excluded on purpose — secrets are
  // never written to sessionStorage; re-enter them after a restore.
  const draft = useDraft("inputs", isNew ? null : input.id, { kind, name, config, enabled }, dirty);
  const restoreDraft = () => { const d = draft.recovered; setKind(d.kind); setName(d.name); setConfig(d.config); setEnabled(d.enabled); draft.restore(); };
  const closeDraft = () => { draft.clear(); onClose(); };
  return html`<${Drawer} open=${true} width=${620} title=${isNew ? t("inputs.newInputTitle") : input.name} onClose=${closeDraft} dirty=${dirty}>
      ${draft.recovered ? html`<${DraftBanner} onRestore=${restoreDraft} onDiscard=${draft.dismiss} />` : null}
      <${FieldErrorSummary} errors=${fieldErrs.errors} />
    <div class="editor">
      ${isNew ? html`<div class="row2">
        <div class="field"><label for="in-name">${t("inputs.fieldName")} <span class="req">*</span></label><input id="in-name" value=${name} onInput=${(e) => setName(e.target.value)} placeholder=${t("inputs.namePlaceholder")} /></div>
        <div class="field"><label for="in-kind">${t("inputs.kindLabel")} <span class="req">*</span></label><select id="in-kind" value=${kind} onChange=${(e) => chooseKind(e.target.value)}>
          <option value="">${t("inputs.chooseOption")}</option>${Object.keys(meta?.inputs || {}).map((k) => html`<option key=${k} value=${k}>${k}</option>`)}</select></div>
      </div>` : html`<p class="muted small mono">${input.kind} · id ${input.id}</p>`}

      ${kind ? fields.map((f) => f.secret
        ? html`<${SecretField} key=${f.name} field=${f} status=${(input.secret_fields_set || {})[f.name]} onChange=${(u) => setSecretEdits((s) => ({ ...s, [f.name]: u }))} />`
        : html`<${FieldInput} key=${f.name} field=${f} value=${config[f.name]} onInput=${(v) => setField(f.name, v)}
            error=${fieldErrs.msgFor(f.name)} onValidity=${(ok) => validity.setValidity(f.name, ok)} />`)
        : html`<p class="muted">${t("inputs.pickKindHint")}</p>`}

      ${kind ? html`<div class="field"><label class="chk"><input type="checkbox" checked=${enabled} onChange=${(e) => setEnabled(e.target.checked)} /> ${t("inputs.enabledLabel")}</label></div>` : null}

      <div class="editor-actions">
        <button class="btn primary" onClick=${save} disabled=${busy || !kind || validity.anyInvalid}>${isNew ? t("inputs.create") : t("inputs.save")}</button>
        ${!isNew ? html`<button class="btn" onClick=${doHealth} disabled=${busy}>${t("inputs.healthBtn")}</button>
          <button class="btn" onClick=${() => setConfirmRestart(true)} disabled=${busy || acting}>${t("inputs.restartBtn")}</button>
          <span class="spacer"></span>
          <button class="btn danger" onClick=${() => setConfirmDel(true)} disabled=${busy}>${t("inputs.deleteBtn")}</button>` : null}
      </div>

      ${health ? html`<div class="result"><b>${t("inputs.healthLabel")}</b> ${health.connected ? html`<span class="badge ok plain">${t("inputs.badgeConnected")}</span>` : html`<span class="badge critical plain">${t("inputs.badgeDown")}</span>`}<${Json} value=${health} /></div>` : null}

      <${KindHelp} help=${tnode(kind ? "inputs.help." + kind : "inputs.help.intro")} />
    </div>
    <${DangerConfirm} open=${confirmDel} token=${input.name} title=${t("inputs.deleteTitle", { name: input.name })}
      warning=${t("inputs.deleteWarning")} busy=${busy}
      onConfirm=${doDelete} onClose=${() => setConfirmDel(false)} />
    <${ConfirmModal} open=${confirmRestart} title=${t("inputs.restartConfirmTitle")}
      message=${t("inputs.restartConfirmBody")} confirmLabel=${t("inputs.restartBtn")}
      onConfirm=${() => { setConfirmRestart(false); restart(); }} onClose=${() => setConfirmRestart(false)} />
  </${Drawer}>`;
}
