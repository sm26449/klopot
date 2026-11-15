// API keys (phase F7): table + create / edit / rotate(grace) / revoke /
// delete, with the plaintext shown exactly once in a copy modal.
import { html, useState, useEffect, useCallback } from "../lib/h.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { Drawer, useDirty, Modal, Spinner, Empty, ErrorState, StaleBanner, DangerConfirm, DraftBanner } from "../lib/ui.js";
import { useDraft } from "../lib/draft.js";
import { useFieldErrors, FieldErrorSummary, fieldErrorId } from "../lib/form.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import { clickable } from "../lib/a11y.js";
import { t } from "../lib/i18n.js";

const SCOPES = [
  ["fire", () => t("apikeys.scopeFire")],
  ["read", () => t("apikeys.scopeRead")],
  ["ack", () => t("apikeys.scopeAck")],
  ["admin", () => t("apikeys.scopeAdmin")],
];

export function ApiKeysView() {
  const [items, setItems] = useState(null);
  const [editing, setEditing] = useState(null);
  const [plaintext, setPlaintext] = useState(null);   // {name, key}
  const [err, setErr] = useState(null); // persistent list-load error (UX-006)

  const load = useCallback(async () => {
    setErr(null);
    try { setItems((await api.get("/v1/api_keys", { limit: 500 })).items); } catch (e) { setErr(e); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return html`<div>
    <div class="page-head">
      <div><h1>${t("apikeys.title")}</h1><p class="muted">${t("apikeys.intro")} <a href="#/api">${t("apikeys.apiRefLink")}</a></p></div>
      <div class="actions"><button class="btn primary" onClick=${() => setEditing({ __new: true })}>${t("apikeys.newKey")}</button></div>
    </div>

    ${err && items ? html`<${StaleBanner} error=${err} onRetry=${load} />` : null}
    ${err && items === null ? html`<${ErrorState} error=${err} onRetry=${load} />` : items === null ? html`<${Spinner} />` : items.length === 0 ? html`<${Empty} title=${t("apikeys.blank.title")} body=${t("apikeys.blank.body")}
        actions=${[{ label: t("apikeys.newKey"), primary: true, onClick: () => setEditing({ __new: true }) }, { label: t("apikeys.blank.reference"), href: "#/api" }]} />`
      : html`<div class="card scroll-x" style="padding:0" tabindex="0" role="region" aria-label=${t("apikeys.tableAria")}>
        <table class="tbl">
          <thead><tr><th>${t("apikeys.colName")}</th><th>${t("apikeys.colPrefix")}</th><th>${t("apikeys.colScopes")}</th><th>${t("apikeys.colState")}</th><th>${t("apikeys.colExpires")}</th><th>${t("apikeys.colLastUsed")}</th></tr></thead>
          <tbody>${items.map((k) => html`<tr key=${k.id} style="cursor:pointer" ...${clickable(() => setEditing(k), t("apikeys.editAria", { name: k.name }))}>
            <td><b>${k.name}</b>${k.rotated_from_id ? html` <span class="muted small">${t("apikeys.rotatedFrom", { id: k.rotated_from_id })}</span>` : null}</td>
            <td class="mono small">${k.key_prefix}…</td>
            <td>${k.scopes.map((s) => html`<span key=${s} class="chip tag">${s}</span>`)}</td>
            <td>${k.enabled ? html`<span class="badge ok plain">${t("apikeys.badgeEnabled")}</span>` : html`<span class="badge plain">${t("apikeys.badgeRevoked")}</span>`}</td>
            <td title=${fmtDateTime(k.expires_at)}>${k.expires_at ? fmtRelative(k.expires_at) : t("apikeys.never")}</td>
            <td title=${fmtDateTime(k.last_used_at)}>${k.last_used_at ? html`${fmtRelative(k.last_used_at)}${k.last_used_ip ? html` <span class="muted small mono">${k.last_used_ip}</span>` : null}` : t("apikeys.never")}</td>
          </tr>`)}</tbody></table></div>`}

    ${editing ? html`<${KeyEditor} apikey=${editing} onClose=${() => setEditing(null)}
        onSaved=${() => { setEditing(null); load(); }} onPlaintext=${(p) => { setEditing(null); setPlaintext(p); load(); }} />` : null}
    ${plaintext ? html`<${PlaintextModal} data=${plaintext} onClose=${() => setPlaintext(null)} />` : null}
  </div>`;
}

function PlaintextModal({ data, onClose }) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  async function copy() { try { await navigator.clipboard.writeText(data.key); setCopied(true); } catch { toast.error(t("apikeys.copyFailed")); } }
  return html`<${Modal} open=${true} title=${t("apikeys.keyCreatedTitle", { name: data.name })} onClose=${saved ? onClose : undefined} width=${520}>
    <div class="alert crit"><b>${t("apikeys.copyNowBold")}</b> ${t("apikeys.copyNowRest")}</div>
    <div class="key-box mono">${data.key}</div>
    <div class="form-actions" style="margin-top:10px">
      <button class="btn" onClick=${copy}>${copied ? t("apikeys.copied") : t("apikeys.copy")}</button>
    </div>
    <label class="chk" style="margin-top:12px"><input type="checkbox" checked=${saved} onChange=${(e) => setSaved(e.target.checked)} /> ${t("apikeys.savedConfirm")}</label>
    <div class="form-actions" style="margin-top:12px; justify-content:flex-end">
      <button class="btn primary" disabled=${!saved} onClick=${onClose}>${t("apikeys.done")}</button>
    </div>
  </${Modal}>`;
}

// Convert a UTC instant (Z-suffixed ISO) to the LOCAL wall-clock string a
// <input type=datetime-local> expects. Slicing the raw UTC string put UTC
// digits into a local-interpreted field, shifting the expiry by the offset
// on every save — even when only scopes were edited (audit F38).
function toLocalDatetimeInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function KeyEditor({ apikey, onClose, onSaved, onPlaintext }) {
  const isNew = !!apikey.__new;
  const [name, setName] = useState(isNew ? "" : apikey.name);
  const [scopes, setScopes] = useState(isNew ? ["fire"] : [...apikey.scopes]);
  const [enabled, setEnabled] = useState(isNew ? true : apikey.enabled);
  const [expires, setExpires] = useState(isNew ? "" : toLocalDatetimeInput(apikey.expires_at));
  const [grace, setGrace] = useState("0");
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const fe = useFieldErrors();
  const nameOk = !isNew || /^[a-z][a-z0-9_-]*$/.test(name);

  function toggleScope(s) { setScopes((cur) => cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]); }
  const expiresIso = expires ? new Date(expires).toISOString() : null;

  async function save() {
    fe.clear();
    if (isNew && !nameOk) return toast.error(t("apikeys.nameRule"));
    if (scopes.length === 0) return toast.error(t("apikeys.pickScope"));
    setBusy(true);
    try {
      if (isNew) {
        const created = await api.post("/v1/api_keys", { name, scopes, enabled, expires_at: expiresIso });
        draft.clear();
        onPlaintext({ name: created.name, key: created.key });
      } else {
        await api.patch(`/v1/api_keys/${apikey.id}`, { scopes, enabled, expires_at: expiresIso });
        toast.ok(t("apikeys.keyUpdated")); draft.clear(); onSaved();
      }
    } catch (e) { if (!fe.show(e)) toast.error(e); } finally { setBusy(false); }
  }
  async function rotate() {
    setBusy(true);
    try { const created = await api.post(`/v1/api_keys/${apikey.id}/rotate`, null, { grace_sec: Number(grace) });
      draft.clear();
      onPlaintext({ name: created.name, key: created.key });
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }
  async function doDelete() {
    setBusy(true);
    try { await api.del(`/v1/api_keys/${apikey.id}`); toast.ok(t("apikeys.keyDeleted")); draft.clear(); onSaved(); }
    catch (e) { toast.error(e); setConfirmDel(false); } finally { setBusy(false); }
  }

  const dirty = useDirty({ name, scopes, enabled, expires, grace });
  const draft = useDraft("apikeys", isNew ? null : apikey.id, { name, scopes, enabled, expires, grace }, dirty);
  const restoreDraft = () => { const d = draft.recovered; setName(d.name); setScopes(d.scopes); setEnabled(d.enabled); setExpires(d.expires); setGrace(d.grace); draft.restore(); };
  const closeDraft = () => { draft.clear(); onClose(); };
  return html`<${Drawer} open=${true} width=${560} title=${isNew ? t("apikeys.newKeyTitle") : apikey.name} onClose=${closeDraft} dirty=${dirty}>
    ${draft.recovered ? html`<${DraftBanner} onRestore=${restoreDraft} onDiscard=${draft.dismiss} />` : null}
    <${FieldErrorSummary} errors=${fe.errors}
      idFor=${(f) => ({ name: "k-name", expires_at: "k-expires" }[f.split(".").pop()] || "k-name")} />
    <div class="editor">
      ${isNew ? html`<div class="field"><label for="k-name">${t("apikeys.fieldName")} <span class="req">*</span></label>
        <input id="k-name" value=${name} onInput=${(e) => setName(e.target.value)}
          aria-invalid=${(name && !nameOk) || !!fe.msgFor("name") || undefined}
          aria-describedby=${fe.msgFor("name") ? fieldErrorId("name") : undefined} placeholder=${t("apikeys.namePlaceholder")} />
        ${fe.msgFor("name") ? html`<div id=${fieldErrorId("name")} class="error small" role="alert">${fe.msgFor("name")}</div>` : null}</div>`
        : html`<p class="muted small mono">${apikey.key_prefix}… · id ${apikey.id}</p>`}

      <fieldset class="field scopes"><legend>${t("apikeys.scopesLegend")}</legend>
        ${SCOPES.map(([s, desc]) => html`<label key=${s} class="chk scope-row">
          <input type="checkbox" checked=${scopes.includes(s)} onChange=${() => toggleScope(s)} />
          <span><b>${s}</b> <span class="muted small">— ${desc()}</span></span></label>`)}</fieldset>

      <div class="row2">
        <div class=${"field" + (fe.msgFor("expires_at") ? " has-error" : "")}><label for="k-expires">${t("apikeys.expiresLabel")}</label>
          <input id="k-expires" type="datetime-local" value=${expires} onInput=${(e) => setExpires(e.target.value)}
            aria-invalid=${fe.msgFor("expires_at") ? "true" : undefined} aria-describedby=${fe.msgFor("expires_at") ? fieldErrorId("expires_at") : undefined} />
          ${fe.msgFor("expires_at") ? html`<div id=${fieldErrorId("expires_at")} class="error small" role="alert">${fe.msgFor("expires_at")}</div>` : null}</div>
        <div class="field"><label class="chk"><input type="checkbox" checked=${enabled} onChange=${(e) => setEnabled(e.target.checked)} /> ${t("apikeys.enabledLabel")}</label></div>
      </div>

      <div class="editor-actions">
        <button class="btn primary" onClick=${save} disabled=${busy}>${isNew ? t("apikeys.create") : t("apikeys.save")}</button>
        ${!isNew && apikey.enabled ? html`<span class="sep"></span>
          <label class="small muted" for="k-grace">${t("apikeys.rotateWithGrace")}</label>
          <select id="k-grace" value=${grace} onChange=${(e) => setGrace(e.target.value)} style="width:auto">
            <option value="0">${t("apikeys.graceNow")}</option><option value="60">60s</option><option value="300">300s</option></select>
          <button class="btn" onClick=${rotate} disabled=${busy}>${t("apikeys.rotate")}</button>` : null}
        ${!isNew ? html`<span class="spacer"></span><button class="btn danger" onClick=${() => setConfirmDel(true)} disabled=${busy}>${t("apikeys.deleteBtn")}</button>` : null}
      </div>
    </div>
    <${DangerConfirm} open=${confirmDel} token=${apikey.name} title=${t("apikeys.deleteKeyTitle", { name: apikey.name })}
      warning=${t("apikeys.deleteWarning")} busy=${busy}
      onConfirm=${doDelete} onClose=${() => setConfirmDel(false)} />
  </${Drawer}>`;
}
