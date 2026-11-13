// Variables (phase F6): table with live value / age / staleness + a
// per-source editor generated from /v1/meta/kinds.
import { html, useState, useEffect } from "../lib/h.js";
import { clickable } from "../lib/a11y.js";
import { useLoader } from "../lib/loader.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { Drawer, useDirty, Spinner, Empty, ErrorState, StaleBanner, DangerConfirm, ListMeta, KindHelp, DraftBanner } from "../lib/ui.js";
import { useDraft } from "../lib/draft.js";
import { FieldInput, useFieldErrors, FieldErrorSummary, configDefaults, useFieldValidity } from "../lib/form.js";
import { fmtRelative } from "../lib/format.js";
import { t, tnode } from "../lib/i18n.js";

const SOURCES = ["mqtt", "aggregate", "constant", "computed", "schedule"];

function fmtVal(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function VariablesView() {
  const [meta, setMeta] = useState(null);
  const [inputs, setInputs] = useState([]);
  const [filters, setFilters] = useState({ source: "", stale: "", search: "" });
  const [editing, setEditing] = useState(null);

  // Debounced + cancelable load with a stale-response guard (audit A28).
  const [page, , reload, error] = useLoader(async (signal) => {
    const q = { limit: 500 };
    if (filters.source) q.source = filters.source;
    if (filters.stale) q.stale = filters.stale;
    if (filters.search) q.search = filters.search;
    return api.get("/v1/variables", q, { signal });
  }, [filters]);
  const items = page?.items ?? null;
  const total = page?.total ?? null;
  useEffect(() => {
    api.get("/v1/meta/kinds").then(setMeta).catch(() => {});
    api.get("/v1/inputs", { limit: 500 }).then((p) => setInputs(p.items)).catch(() => {});
  }, []);

  function setF(k, v) { setFilters((f) => ({ ...f, [k]: v })); }

  return html`<div>
    <div class="page-head">
      <div><h1>${t("variables.title")}</h1><p class="muted">${t("variables.subtitle")}</p></div>
      <div class="actions"><button class="btn primary" onClick=${() => setEditing({ __new: true })}>${t("variables.newVariable")}</button></div>
    </div>

    <div class="card filters">
      <input class="grow" aria-label=${t("variables.searchAria")} placeholder=${t("variables.searchPlaceholder")} value=${filters.search} onInput=${(e) => setF("search", e.target.value)} />
      <select aria-label=${t("variables.filterSourceAria")} value=${filters.source} onChange=${(e) => setF("source", e.target.value)}>
        <option value="">${t("variables.anySource")}</option>${SOURCES.map((s) => html`<option key=${s} value=${s}>${s}</option>`)}</select>
      <select aria-label=${t("variables.filterStaleAria")} value=${filters.stale} onChange=${(e) => setF("stale", e.target.value)}>
        <option value="">${t("variables.freshAndStale")}</option><option value="true">${t("variables.staleOnly")}</option><option value="false">${t("variables.freshOnly")}</option></select>
    </div>

    <${ListMeta} total=${total} limit=${500} />
    ${error && items ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    <div class="card" style="margin-top:14px; padding:0">
      ${error && items === null ? html`<${ErrorState} error=${error} onRetry=${reload} />` : items === null ? html`<${Spinner} />` : items.length === 0 ? html`<${Empty} label=${t("variables.empty")} />`
        : html`<table class="tbl"><thead><tr><th>${t("variables.thName")}</th><th>${t("variables.thSource")}</th><th>${t("variables.thValue")}</th><th>${t("variables.thAge")}</th><th>${t("variables.thState")}</th></tr></thead>
          <tbody>${items.map((v) => html`<tr key=${v.id} ...${clickable(() => setEditing(v), t("variables.editAria", { name: v.name }))} style="cursor:pointer">
            <td><b>${v.name}</b><div class="muted small mono">${v.config?.topic || v.config?.json_path || ""}</div></td>
            <td class="mono small">${v.source}</td>
            <td class="mono">${fmtVal(v.last_value)}</td>
            <td title=${v.last_value_at || ""}>${v.age_sec == null ? "—" : fmtRelative(new Date(Date.now() - v.age_sec * 1000).toISOString())}</td>
            <td>${!v.enabled ? html`<span class="badge plain">${t("variables.stateOff")}</span>`
              : v.is_stale ? html`<span class="badge warning plain">${t("variables.stateStale")}</span>`
              : v.last_value != null ? html`<span class="badge ok plain">${t("variables.stateLive")}</span>` : html`<span class="badge plain">—</span>`}</td>
          </tr>`)}</tbody></table>`}
    </div>

    ${editing ? html`<${VariableEditor} variable=${editing} meta=${meta} inputs=${inputs}
        onClose=${() => setEditing(null)} onSaved=${() => { setEditing(null); reload(); }} />` : null}
  </div>`;
}

function VariableEditor({ variable, meta, inputs, onClose, onSaved }) {
  const isNew = !!variable.__new;
  const [name, setName] = useState(isNew ? "" : variable.name);
  const [source, setSource] = useState(isNew ? "mqtt" : variable.source);
  const [inputId, setInputId] = useState(isNew ? null : variable.input_id);
  const [config, setConfig] = useState(isNew ? {} : { ...(variable.config || {}) });
  const [description, setDescription] = useState(isNew ? "" : variable.description || "");
  const [enabled, setEnabled] = useState(isNew ? true : variable.enabled);
  const [busy, setBusy] = useState(false);
  const fieldErrs = useFieldErrors();
  const [confirmDel, setConfirmDel] = useState(false);

  const validity = useFieldValidity();
  // meta fields for this source, minus input_id (handled as a column).
  const fields = (meta?.variables?.[source]?.fields || []).filter((f) => f.name !== "input_id");
  const needsInput = source === "mqtt" || source === "aggregate";

  function setField(n, v) { setConfig((c) => ({ ...c, [n]: v })); }
  function chooseSource(s) { setSource(s); setConfig(configDefaults(meta?.variables?.[s]?.fields)); validity.reset(); }

  async function save() {
    fieldErrs.clear();
    if (isNew && !/^[a-zA-Z][a-zA-Z0-9_.]*$/.test(name)) return toast.error(t("variables.nameRule"));
    if (validity.anyInvalid) { validity.focusFirst(); return toast.error(t("variables.fixJson")); }
    setBusy(true);
    try {
      const payload = { source, input_id: inputId ? Number(inputId) : null, config, description: description || null, enabled };
      if (isNew) await api.post("/v1/variables", { name, ...payload });
      else await api.patch(`/v1/variables/${encodeURIComponent(variable.name)}`, payload);
      toast.ok(isNew ? t("variables.created") : t("variables.saved"));
      draft.clear();
      onSaved();
    } catch (e) { if (!fieldErrs.show(e)) toast.error(e); } finally { setBusy(false); }
  }
  async function doDelete() {
    setBusy(true);
    try { await api.del(`/v1/variables/${encodeURIComponent(variable.name)}`); toast.ok(t("variables.deleted")); draft.clear(); onSaved(); }
    catch (e) { toast.error(e); setConfirmDel(false); } finally { setBusy(false); }
  }

  const dirty = useDirty({ name, source, inputId, config, description, enabled }) || validity.anyInvalid;
  const draft = useDraft("variables", isNew ? null : variable.id, { name, source, inputId, config, description, enabled }, dirty);
  const restoreDraft = () => { const d = draft.recovered; setName(d.name); setSource(d.source); setInputId(d.inputId); setConfig(d.config); setDescription(d.description); setEnabled(d.enabled); draft.restore(); };
  const closeDraft = () => { draft.clear(); onClose(); };
  return html`<${Drawer} open=${true} width=${600} title=${isNew ? t("variables.newVariable") : variable.name} onClose=${closeDraft} dirty=${dirty}>
      ${draft.recovered ? html`<${DraftBanner} onRestore=${restoreDraft} onDiscard=${draft.dismiss} />` : null}
      <${FieldErrorSummary} errors=${fieldErrs.errors} />
    <div class="editor">
      ${isNew ? html`<div class="row2">
        <div class="field"><label for="v-name">${t("variables.nameLabel")} <span class="req">*</span></label><input id="v-name" value=${name} onInput=${(e) => setName(e.target.value)} placeholder=${t("variables.namePlaceholder")} /></div>
        <div class="field"><label for="v-source">${t("variables.sourceLabel")}</label><select id="v-source" value=${source} onChange=${(e) => chooseSource(e.target.value)}>${SOURCES.map((s) => html`<option key=${s} value=${s}>${s}</option>`)}</select></div>
      </div>` : html`<p class="muted small mono">${variable.source} · id ${variable.id}${variable.last_value != null ? ` · ${t("variables.livePrefix")} ${fmtVal(variable.last_value)}` : ""}</p>`}

      ${needsInput ? html`<div class="field"><label for="v-input">${t("variables.inputLabel")}</label>
        <select id="v-input" value=${inputId ?? ""} onChange=${(e) => setInputId(e.target.value || null)}>
          <option value="">${t("variables.inputNone")}</option>${inputs.map((i) => html`<option key=${i.id} value=${i.id}>${i.name} (${i.kind})</option>`)}</select></div>` : null}

      ${fields.map((f) => html`<${FieldInput} key=${f.name} field=${f} value=${config[f.name]} onInput=${(v) => setField(f.name, v)}
        error=${fieldErrs.msgFor(f.name)} onValidity=${(ok) => validity.setValidity(f.name, ok)} />`)}

      <div class="field"><label for="v-desc">${t("variables.descriptionLabel")}</label><textarea id="v-desc" rows="2" value=${description} onInput=${(e) => setDescription(e.target.value)}></textarea></div>
      <div class="field"><label class="chk"><input type="checkbox" checked=${enabled} onChange=${(e) => setEnabled(e.target.checked)} /> ${t("variables.enabledLabel")}</label></div>

      <div class="editor-actions">
        <button class="btn primary" onClick=${save} disabled=${busy || validity.anyInvalid}>${isNew ? t("variables.create") : t("variables.save")}</button>
        ${!isNew ? html`<span class="spacer"></span><button class="btn danger" onClick=${() => setConfirmDel(true)} disabled=${busy}>${t("variables.delete")}</button>` : null}
      </div>

      <${KindHelp} help=${tnode("variables.help." + source)} />
    </div>
    <${DangerConfirm} open=${confirmDel} token=${variable.name} title=${t("variables.deleteTitle", { name: variable.name })}
      warning=${t("variables.deleteWarning")} busy=${busy}
      onConfirm=${doDelete} onClose=${() => setConfirmDel(false)} />
  </${Drawer}>`;
}
