// Variables (phase F6): table with live value / age / staleness + a
// per-source editor generated from /v1/meta/kinds.
import { html, useState, useEffect, useMemo } from "../lib/h.js";
import { useUrlFilters } from "../lib/router.js";
import { TransferMenu } from "../lib/transfer.js";
import { clickable } from "../lib/a11y.js";
import { useLoader } from "../lib/loader.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { Drawer, useDirty, Spinner, Empty, ErrorState, StaleBanner, DangerConfirm, ListMeta, KindHelp, DraftBanner, starterActions } from "../lib/ui.js";
import { useDraft } from "../lib/draft.js";
import { FieldInput, useFieldErrors, FieldErrorSummary, FieldMsg, configDefaults, useFieldValidity } from "../lib/form.js";
import { fmtRelative } from "../lib/format.js";
import { t, tnode } from "../lib/i18n.js";

const SOURCES = ["mqtt", "aggregate", "constant", "computed", "schedule"];

function fmtVal(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function VariablesView({ query }) {
  const [meta, setMeta] = useState(null);
  const [inputs, setInputs] = useState([]);
  // Filters ride the URL so a link like #/variables?state=missing works.
  const [filters, setF, resetF] = useUrlFilters("/variables", query, { search: "", source: "", state: "", input_id: "", used: "" });
  const [editing, setEditing] = useState(null);
  // Groups start collapsed (an overview of the namespaces) and open by
  // themselves while a filter narrows the list; a click flips one group.
  const filtering = Object.values(filters).some(Boolean);
  const [flipped, setFlipped] = useState(() => new Set());
  useEffect(() => { setFlipped(new Set()); }, [filtering]);

  // Debounced + cancelable load with a stale-response guard (audit A28).
  const [page, , reload, error] = useLoader(async (signal) => {
    const q = { limit: 500 };
    for (const k of Object.keys(filters)) if (filters[k]) q[k] = filters[k];
    return api.get("/v1/variables", q, { signal });
  }, [filters]);
  const items = page?.items ?? null;
  const total = page?.total ?? null;
  useEffect(() => {
    api.get("/v1/meta/kinds").then(setMeta).catch(() => {});
    api.get("/v1/inputs", { limit: 500 }).then((p) => setInputs(p.items)).catch(() => {});
  }, []);

  const inputName = useMemo(() => new Map(inputs.map((i) => [i.id, i.name])), [inputs]);
  const groups = useMemo(() => groupByNamespace(items || []), [items]);
  const isOpen = (ns) => filtering !== flipped.has(ns);
  const flip = (ns) => setFlipped((f) => { const n = new Set(f); if (n.has(ns)) n.delete(ns); else n.add(ns); return n; });
  const allOpen = groups.length > 0 && groups.every(([ns]) => isOpen(ns));
  const setAll = (open) => setFlipped(open === filtering ? new Set() : new Set(groups.map(([ns]) => ns)));

  return html`<div>
    <div class="page-head">
      <div><h1>${t("variables.title")}</h1><p class="muted">${t("variables.subtitle")}</p></div>
      <div class="actions">
        <${TransferMenu} section="variables" shownNames=${(items || []).map((x) => x.name)}
          filtered=${filtering} onImported=${reload} />
        <button class="btn primary" onClick=${() => setEditing({ __new: true })}>${t("variables.newVariable")}</button></div>
    </div>

    <div class="card filters">
      <input class="grow" aria-label=${t("variables.searchAria")} placeholder=${t("variables.searchPlaceholder")} value=${filters.search} onInput=${(e) => setF("search", e.target.value)} />
      <select aria-label=${t("variables.filterSourceAria")} value=${filters.source} onChange=${(e) => setF("source", e.target.value)}>
        <option value="">${t("variables.anySource")}</option>${SOURCES.map((s) => html`<option key=${s} value=${s}>${s}</option>`)}</select>
      <select aria-label=${t("variables.filterInputAria")} value=${filters.input_id} onChange=${(e) => setF("input_id", e.target.value)}>
        <option value="">${t("variables.anyInput")}</option>${inputs.map((i) => html`<option key=${i.id} value=${String(i.id)}>${i.name}</option>`)}</select>
      <select aria-label=${t("variables.filterStaleAria")} value=${filters.state} onChange=${(e) => setF("state", e.target.value)}>
        <option value="">${t("variables.anyValueState")}</option>
        <option value="fresh">${t("variables.freshOnly")}</option><option value="stale">${t("variables.staleOnly")}</option>
        <option value="missing">${t("variables.missingOnly")}</option></select>
      <select aria-label=${t("variables.filterUsedAria")} value=${filters.used} onChange=${(e) => setF("used", e.target.value)}>
        <option value="">${t("variables.usedAny")}</option><option value="true">${t("variables.usedOnly")}</option><option value="false">${t("variables.unusedOnly")}</option></select>
    </div>

    <div class="list-toolbar">
      <${ListMeta} total=${total} limit=${500} />
      ${groups.length > 1 ? html`<button class="btn sm" onClick=${() => setAll(!allOpen)}>${allOpen ? t("variables.collapseAll") : t("variables.expandAll")}</button>` : null}
    </div>
    ${error && items ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    ${error && items === null ? html`<div class="card"><${ErrorState} error=${error} onRetry=${reload} /></div>`
      : items === null ? html`<div class="card"><${Spinner} /></div>`
      : items.length === 0 ? html`<div class="card">${Object.values(filters).some(Boolean)
        ? html`<${Empty} filtered onClear=${resetF} />`
        : html`<${Empty} title=${t("variables.blank.title")} body=${t("variables.blank.body")}
            actions=${[{ label: t("variables.newVariable"), primary: true, onClick: () => setEditing({ __new: true }) },
              { label: t("variables.blank.inputs"), href: "#/inputs" }, ...starterActions()]} />`}</div>`
      : groups.map(([ns, vars]) => html`<${VariableGroup} key=${ns} ns=${ns} vars=${vars} open=${isOpen(ns)}
          onToggle=${() => flip(ns)} inputName=${inputName} onOpen=${setEditing} />`)}

    ${editing ? html`<${VariableEditor} variable=${editing} meta=${meta} inputs=${inputs}
        onClose=${() => setEditing(null)} onSaved=${() => { setEditing(null); reload(); }} />` : null}
  </div>`;
}

// "grid.power" → "grid"; names without a dot share one group.
export function namespaceOf(name) {
  const i = name.indexOf(".");
  return i > 0 ? name.slice(0, i) : "";
}

export function groupByNamespace(vars) {
  const groups = new Map();
  for (const v of vars) {
    const ns = namespaceOf(v.name);
    if (!groups.has(ns)) groups.set(ns, []);
    groups.get(ns).push(v);
  }
  return [...groups.entries()].sort((a, b) => (a[0] === "") - (b[0] === "") || a[0].localeCompare(b[0]));
}

function usedCount(v) { return (v.used_by_rules?.length || 0) + (v.used_by_variables?.length || 0); }

function ValueState({ v }) {
  if (!v.enabled) return html`<span class="badge plain">${t("variables.stateOff")}</span>`;
  if (v.value_state === "stale") return html`<span class="badge warning plain">${t("variables.stateStale")}</span>`;
  if (v.value_state === "missing") return html`<span class="badge plain" title=${t("variables.missingTitle")}>${t("variables.stateMissing")}</span>`;
  return html`<span class="badge ok plain">${t("variables.stateLive")}</span>`;
}

function VariableGroup({ ns, vars, open, onToggle, inputName, onOpen }) {
  const count = (state) => vars.filter((v) => v.enabled && v.value_state === state).length;
  const stale = count("stale");
  const missing = count("missing");
  const unused = vars.filter((v) => usedCount(v) === 0).length;
  const label = ns || t("variables.noNamespace");
  const bodyId = `vg-${(ns || "_root").replace(/[^\w-]/g, "_")}`;
  return html`<section class="card var-group">
    <h2 class="group-head">
      <button class="group-toggle mono" aria-expanded=${open} aria-controls=${bodyId} onClick=${onToggle}>
        <span class="caret" aria-hidden="true">${open ? "▾" : "▸"}</span> ${label}
      </button>
      <span class="muted small">${t("variables.groupSummary", { count: vars.length })}</span>
      ${stale ? html`<span class="badge warning plain small">${t("variables.groupStale", { count: stale })}</span>` : null}
      ${missing ? html`<span class="badge plain small">${t("variables.groupMissing", { count: missing })}</span>` : null}
      ${unused ? html`<span class="badge plain small">${t("variables.groupUnused", { count: unused })}</span>` : null}
    </h2>
    ${open ? html`<div id=${bodyId} class="scroll-x"><table class="tbl">
      <thead><tr><th>${t("variables.thName")}</th><th>${t("variables.thSource")}</th><th>${t("variables.thValue")}</th>
        <th>${t("variables.thAge")}</th><th>${t("variables.thState")}</th><th>${t("variables.thUsedBy")}</th></tr></thead>
      <tbody>${vars.map((v) => html`<tr key=${v.id} ...${clickable(() => onOpen(v), t("variables.editAria", { name: v.name }))} style="cursor:pointer">
        <td><b class="mono">${v.name}</b>
          <div class="muted small mono">${v.config?.topic || v.config?.formula || (v.config?.topics ? t("variables.topicsCount", { count: v.config.topics.length }) : "")}</div>
          ${v.description ? html`<div class="muted small">${v.description}</div>` : null}</td>
        <td class="small"><span class="mono">${v.source}</span>${v.input_id && inputName.get(v.input_id) ? html`<div class="muted">${inputName.get(v.input_id)}</div>` : null}</td>
        <td class="mono">${fmtVal(v.last_value)}</td>
        <td title=${v.last_value_at || ""}>${v.age_sec == null ? "—" : fmtRelative(new Date(Date.now() - v.age_sec * 1000).toISOString())}</td>
        <td><${ValueState} v=${v} /></td>
        <td class="small" title=${[...(v.used_by_rules || []), ...(v.used_by_variables || [])].join(", ")}>
          ${usedCount(v) ? t("variables.usedBySummary", { rules: v.used_by_rules?.length || 0, vars: v.used_by_variables?.length || 0 })
            : html`<span class="muted">${t("variables.unused")}</span>`}</td>
      </tr>`)}</tbody></table></div>` : null}
  </section>`;
}

// Who reads this variable, with links (in the editor, not the table row, so
// rows stay a single interactive control).
function UsedBy({ variable }) {
  const rules = variable.used_by_rules || [];
  const vars = variable.used_by_variables || [];
  if (!rules.length && !vars.length) return html`<p class="muted small">${t("variables.usedByNone")}</p>`;
  return html`<div class="field"><span class="label-like">${t("variables.usedByLabel")}</span>
    <div class="chips">
      ${rules.map((r) => html`<a key=${"r:" + r} class="chip tag" href=${"#/rules?search=" + encodeURIComponent(r)}>${t("variables.ruleChip", { name: r })}</a>`)}
      ${vars.map((n) => html`<a key=${"v:" + n} class="chip" href=${"#/variables?search=" + encodeURIComponent(n)}>${t("variables.varChip", { name: n })}</a>`)}
    </div></div>`;
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
    if (!fieldErrs.check([["name", !isNew || /^[a-zA-Z][a-zA-Z0-9_.]*$/.test(name), name ? t("variables.nameRule") : null]])) return;
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
      <${FieldErrorSummary} errors=${fieldErrs.errors}
        idFor=${(f) => (f.split(".").pop() === "name" ? "v-name" : "f_" + f.split(".").pop())} />
    <div class="editor">
      ${isNew ? html`<div class="row2">
        <div class="field"><label for="v-name">${t("variables.nameLabel")} <span class="req">*</span></label><input id="v-name" value=${name} onInput=${(e) => setName(e.target.value)} placeholder=${t("variables.namePlaceholder")} ...${fieldErrs.attrs("name")} />
          <${FieldMsg} fe=${fieldErrs} name="name" /></div>
        <div class="field"><label for="v-source">${t("variables.sourceLabel")}</label><select id="v-source" value=${source} onChange=${(e) => chooseSource(e.target.value)}>${SOURCES.map((s) => html`<option key=${s} value=${s}>${s}</option>`)}</select></div>
      </div>` : html`<p class="muted small mono">${variable.source} · id ${variable.id}${variable.last_value != null ? ` · ${t("variables.livePrefix")} ${fmtVal(variable.last_value)}` : ""}</p>
        <${UsedBy} variable=${variable} />`}

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
      warning=${(variable.used_by_rules?.length || variable.used_by_variables?.length)
        ? `${t("variables.deleteWarning")} ${t("variables.deleteInUse", { names: [...(variable.used_by_rules || []), ...(variable.used_by_variables || [])].join(", ") })}`
        : t("variables.deleteWarning")} busy=${busy}
      onConfirm=${doDelete} onClose=${() => setConfirmDel(false)} />
  </${Drawer}>`;
}
