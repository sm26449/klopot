// Rules (phase F6): table + editor with live validation, an expression
// cheat-sheet, eval-now, test fire, duplicate and typed-confirm delete.
import { html, useState, useEffect, useMemo } from "../lib/h.js";
import { useLoader } from "../lib/loader.js";
import { api, getAll } from "../lib/api.js";
import { lookup } from "../lib/lookup.js";
import { navigate, useUrlFilters } from "../lib/router.js";
import { toast } from "../lib/toast.js";
import { Drawer, useDirty, Spinner, Empty, ErrorState, StaleBanner, ListMeta, DangerConfirm, Json, KindHelp, DraftBanner, starterActions } from "../lib/ui.js";
import { canonicalCategories, categoryLabels } from "../lib/categories.js";
import { TransferMenu, downloadPack } from "../lib/transfer.js";
import { useDraft } from "../lib/draft.js";
import { TagInput, useFieldErrors, FieldErrorSummary, fieldErrorId } from "../lib/form.js";
import { fmtRelative, fmtDateTime, fmtSeconds } from "../lib/format.js";
import { sevLabel } from "../lib/labels.js";
import { t, tnode } from "../lib/i18n.js";
import { ExprInput, cheatRows } from "../lib/expr.js";

const LIMIT = 500;

// Outcome of POST /v1/rules/validate under an expression field: ok / error,
// the variables it reads (with live value and age) and the unknown ones.
function ValidationResult({ validation }) {
  if (!validation) return null;
  return html`
    <span>${validation.ok ? html`<span class="badge ok plain">${t("rules.validateOk", { result: JSON.stringify(validation.result) })}</span>`
      : html`<span class="badge critical plain">${t("rules.badgeError")}</span> <span class="error small">${validation.error}</span>`}</span>
    <div class="validation">
      ${validation.referenced_vars?.length ? html`<div class="small"><b>${t("rules.referenced")}</b> ${validation.referenced_vars.map((v) => html`<span key=${v.name} class=${"chip " + (v.present ? (v.is_stale ? "warn" : "") : "crit")}
        title=${v.present ? t("rules.varPresentTitle", { value: JSON.stringify(v.live_value), age: Math.round(v.age_sec), stale: v.is_stale ? t("rules.varStaleSuffix") : "" }) : t("rules.varUnknown")}>${v.name}</span>`)}</div>` : null}
      ${validation.unknown_vars?.length ? html`<div class="small warn-text">${t("rules.unknownVars", { vars: validation.unknown_vars.join(", ") })}</div>` : null}
    </div>`;
}

// One badge for the list: disabled rules show their last error as history
// (audit V21); enabled ones distinguish a failing expression from a rule that
// is only waiting for an input (eval_status).
export function RuleStatusBadge({ rule: r }) {
  if (!r.enabled) {
    return r.eval_status === "ok"
      ? html`<span class="badge plain">${t("rules.badgeOff")}</span>`
      : html`<span class="badge plain" title=${t("rules.disabledLastErrorTitle", { error: r.last_eval_error || "" })}>${t("rules.badgeOffLastError")}</span>`;
  }
  if (r.eval_status === "error") return html`<span class="badge warning plain" title=${r.last_eval_error || ""}>${t("rules.badgeError")}</span>`;
  if (r.eval_status === "no_data") return html`<span class="badge plain" title=${r.last_eval_error || ""}>${t("rules.badgeNoData")}</span>`;
  return html`<span class="badge ok plain">${t("rules.badgeOn")}</span>`;
}

export function RulesView({ query, params }) {
  // Filters live in the URL so they survive reload/back/forward and deep-links
  // (UX-015). The whole filtered set is loaded (≤ 500) and grouped by the
  // category of each rule's template; ListMeta warns if the set is truncated.
  const [filters, setF, resetF] = useUrlFilters("/rules", query, {
    template_type: "", enabled: "", eval_status: "", search: "", category: "", never_fired: "",
  });
  const [templateRows, setTemplateRows] = useState([]);
  const [variables, setVariables] = useState([]);
  const [allRules, setAllRules] = useState([]);
  const [editing, setEditing] = useState(null);
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState(false);

  // Deep-link (/rules/:id, e.g. from an alert's "rule #N"): open that rule,
  // fetching it even if it isn't in the current list; a missing id falls back
  // to the list with a message (UX-014).
  useEffect(() => {
    const id = params && params.id;
    if (!id) return undefined;
    let active = true;
    api.get(`/v1/rules/${encodeURIComponent(id)}`)
      .then((r) => { if (active) setEditing(r); })
      // Only a 404 means "no such rule"; a network or server error says what it is (UX-14).
      .catch((e) => { if (active) { toast.error(e && e.status === 404 ? t("rules.notFound", { id }) : e); navigate("/rules"); } });
    return () => { active = false; };
  }, [params && params.id]);
  // force: the Drawer's dirty guard already confirmed, so don't re-ask here.
  const closeEditor = () => { setEditing(null); if (params && params.id) navigate("/rules", null, { force: true }); };

  // Debounced + cancelable load with a stale-response guard (audit A28).
  const [data, , reload, error] = useLoader((signal) => {
    const q = { limit: LIMIT };
    for (const k of ["template_type", "enabled", "eval_status", "search", "category", "never_fired"]) {
      if (filters[k]) q[k] = filters[k];
    }
    return api.get("/v1/rules", q, { signal });
  }, [filters]);

  useEffect(() => {
    lookup(getAll("/v1/templates").then((p) => setTemplateRows(p.items)));
    lookup(getAll("/v1/variables").then((p) => setVariables(p.items.map((v) => v.name).sort())));
    lookup(getAll("/v1/rules").then((p) => setAllRules(p.items.map((r) => r.name).sort())));
  }, []);

  const templates = useMemo(() => templateRows.map((tt) => tt.type).sort(), [templateRows]);
  const categories = useMemo(() => canonicalCategories(templateRows), [templateRows]);
  const items = data?.items || [];
  const groups = useMemo(() => groupRules(items, templateRows), [items, templateRows]);

  // Rules needing attention, across the WHOLE set (not just what the filters
  // show): only ENABLED rules count — a disabled rule keeps its last error as
  // history and must not be surfaced as failing now (audit V21). Expression
  // errors and rules waiting for an input are reported separately.
  // Every such rule (not the first 100), and a failed lookup is said, not
  // shown as "nothing failing" (Copilot hygiene #7).
  const [attention, setAttention] = useState({ error: [], no_data: [], failed: false });
  useEffect(() => {
    let active = true;
    const load = (status) => getAll("/v1/rules", { enabled: "true", eval_status: status }).then((p) => p.items);
    Promise.all([load("error"), load("no_data")]).then(([error, noData]) => {
      if (active) setAttention({ error, no_data: noData, failed: false });
    }).catch(() => { if (active) setAttention({ error: [], no_data: [], failed: true }); });
    return () => { active = false; };
  }, [data]);

  // Drop selections that the current filters no longer show.
  useEffect(() => {
    const visible = new Set(items.map((r) => r.id));
    setSelected((s) => new Set([...s].filter((id) => visible.has(id))));
  }, [data]);

  const toggleGroup = (label) => setCollapsed((c) => {
    const n = new Set(c); if (n.has(label)) n.delete(label); else n.add(label); return n;
  });
  const allCollapsed = groups.length > 0 && groups.every(([label]) => collapsed.has(label));
  const select = (ids, on) => setSelected((s) => {
    const n = new Set(s); for (const id of ids) { if (on) n.add(id); else n.delete(id); } return n;
  });

  async function exportSelected() {
    const names = items.filter((r) => selected.has(r.id)).map((r) => r.name);
    try { await downloadPack({ sections: "rules", names: names.join(","), with_dependencies: true }, "klopot-rules-selected"); }
    catch (e) { toast.error(e); }
  }

  async function bulkEnable(enabled) {
    if (busy || selected.size === 0) return;
    setBusy(true);
    try {
      const r = await api.post("/v1/rules/bulk/enabled", { ids: [...selected], enabled });
      toast.ok(t(enabled ? "rules.bulkEnabled" : "rules.bulkDisabled", { count: r.updated.length, unchanged: r.unchanged.length }));
      setSelected(new Set());
      reload();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  return html`<div>
    <div class="page-head">
      <div><h1>${t("rules.title")}</h1><p class="muted">${t("rules.subtitle")}</p></div>
      <div class="actions">
        <${TransferMenu} section="rules" shownNames=${items.map((r) => r.name)}
          filtered=${Object.values(filters).some(Boolean)} onImported=${reload} />
        <button class="btn primary" onClick=${() => setEditing({ __new: true })}>${t("rules.newRule")}</button></div>
    </div>

    ${attention.failed ? html`<div class="alert warn" role="status">${t("rules.attentionFailed")}</div>` : null}
    ${["error", "no_data"].map((kind) => attention[kind].length ? html`<div key=${kind} class=${"alert " + (kind === "error" ? "warn" : "info")}>
      <b>${t(kind === "error" ? "rules.evalErrorsBanner" : "rules.noDataBanner", { count: attention[kind].length })}</b>
      ${attention[kind].map((r) => html` <a key=${r.id} class="mono small" href=${"#/rules/" + r.id} title=${r.last_eval_error || ""}>${r.name}</a>`)}
    </div>` : null)}

    <div class="card filters">
      <input class="grow" aria-label=${t("rules.searchAria")} placeholder=${t("rules.searchPlaceholder")} value=${filters.search} onInput=${(e) => setF("search", e.target.value)} />
      <select aria-label=${t("rules.filterCategoryAria")} value=${filters.category} onChange=${(e) => setF("category", e.target.value)}>
        <option value="">${t("rules.anyCategory")}</option>
        ${categories.map((c) => html`<option key=${c} value=${c}>${c}</option>`)}
        <option value="__none__">${t("rules.uncategorized")}</option></select>
      <select aria-label=${t("rules.filterTemplateAria")} value=${filters.template_type} onChange=${(e) => setF("template_type", e.target.value)}>
        <option value="">${t("rules.anyTemplate")}</option>${templates.map((tt) => html`<option key=${tt} value=${tt}>${tt}</option>`)}</select>
      <select aria-label=${t("rules.filterStateAria")} value=${filters.enabled} onChange=${(e) => setF("enabled", e.target.value)}>
        <option value="">${t("rules.anyState")}</option><option value="true">${t("rules.enabled")}</option><option value="false">${t("rules.disabled")}</option></select>
      <select aria-label=${t("rules.filterErrorAria")} value=${filters.eval_status} onChange=${(e) => setF("eval_status", e.target.value)}>
        <option value="">${t("rules.all")}</option><option value="error">${t("rules.withErrors")}</option>
        <option value="no_data">${t("rules.statusNoData")}</option><option value="ok">${t("rules.statusOk")}</option></select>
      <select aria-label=${t("rules.filterFiredAria")} value=${filters.never_fired} onChange=${(e) => setF("never_fired", e.target.value)}>
        <option value="">${t("rules.firedAny")}</option><option value="true">${t("rules.neverFired")}</option><option value="false">${t("rules.hasFired")}</option></select>
    </div>

    <div class="list-toolbar">
      <${ListMeta} total=${data?.total ?? null} limit=${LIMIT} />
      ${groups.length > 1 ? html`<button class="btn sm" onClick=${() => setCollapsed(allCollapsed ? new Set() : new Set(groups.map(([g]) => g)))}>
        ${allCollapsed ? t("rules.expandAll") : t("rules.collapseAll")}</button>` : null}
    </div>

    ${selected.size ? html`<div class="bulk-bar card" role="region" aria-label=${t("rules.bulkAria")}>
      <b>${t("rules.selectedCount", { count: selected.size })}</b>
      <button class="btn sm" disabled=${busy} onClick=${() => bulkEnable(true)}>${t("rules.bulkEnable")}</button>
      <button class="btn sm" disabled=${busy} onClick=${() => bulkEnable(false)}>${t("rules.bulkDisable")}</button>
      <button class="btn sm" disabled=${busy} onClick=${exportSelected}>${t("rules.bulkExport")}</button>
      <button class="btn sm" disabled=${busy} onClick=${() => setSelected(new Set())}>${t("rules.clearSelection")}</button>
    </div>` : null}

    ${error && data ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    ${error && !data ? html`<div class="card"><${ErrorState} error=${error} onRetry=${reload} /></div>`
      : data === null ? html`<div class="card"><${Spinner} /></div>`
      : items.length === 0 ? html`<div class="card">${Object.values(filters).some(Boolean)
        ? html`<${Empty} filtered onClear=${resetF} />`
        : html`<${Empty} title=${t("rules.blank.title")} body=${t("rules.blank.body")}
            actions=${[{ label: t("rules.newRule"), primary: true, onClick: () => setEditing({ __new: true }) }, ...starterActions()]} />`}</div>`
      : groups.map(([label, rules]) => html`<${RuleGroup} key=${label} label=${label} rules=${rules}
          open=${!collapsed.has(label)} onToggle=${() => toggleGroup(label)}
          selected=${selected} onSelect=${select} onOpen=${setEditing} />`)}

    ${editing ? html`<${RuleEditor} key=${editing.__new ? "new:" + (editing.name || "") : "id:" + editing.id}
        rule=${editing} templateRows=${templateRows} variables=${variables} rules=${allRules}
        onClose=${closeEditor} onSaved=${() => { closeEditor(); reload(); }}
        onDuplicate=${(r) => setEditing(r)} />` : null}
  </div>`;
}

// [[label, rules]] grouped by the category of each rule's template (case-
// insensitive, most used spelling), sorted by label with "Uncategorized" last.
export function groupRules(rules, templateRows) {
  const labels = categoryLabels(templateRows);
  const categoryOf = new Map(templateRows.map((tt) => [tt.type, tt.category]));
  const none = t("rules.uncategorized");
  const groups = new Map();
  for (const r of rules) {
    const c = categoryOf.get(r.template_type);
    const label = c ? labels.get(c.toLowerCase()) || c : none;
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(r);
  }
  return [...groups.entries()].sort((a, b) =>
    (a[0] === none) - (b[0] === none) || a[0].localeCompare(b[0]));
}

function RuleGroup({ label, rules, open, onToggle, selected, onSelect, onOpen }) {
  const on = rules.filter((r) => r.enabled).length;
  const issues = rules.filter((r) => r.enabled && r.eval_status !== "ok").length;
  const ids = rules.map((r) => r.id);
  const allSelected = ids.every((id) => selected.has(id));
  const bodyId = `rg-${label.replace(/[^\w-]/g, "_")}`;
  return html`<section class="card rule-group">
    <h2 class="group-head">
      <button class="group-toggle" aria-expanded=${open} aria-controls=${bodyId} onClick=${onToggle}>
        <span class="caret" aria-hidden="true">${open ? "▾" : "▸"}</span> ${label}
      </button>
      <span class="muted small">${t("rules.groupSummary", { count: rules.length, on })}</span>
      ${issues ? html`<span class="badge warning plain small">${t("rules.groupIssues", { count: issues })}</span>` : null}
    </h2>
    ${open ? html`<div id=${bodyId} class="scroll-x"><table class="tbl">
      <thead><tr>
        <th class="sel"><input type="checkbox" aria-label=${t("rules.selectGroupAria", { group: label })}
          checked=${allSelected} onChange=${(e) => onSelect(ids, e.target.checked)} /></th>
        <th>${t("rules.colName")}</th><th>${t("rules.colTemplate")}</th><th>${t("rules.colState")}</th>
        <th>${t("rules.colPersist")}</th><th>${t("rules.colLastFired")}</th><th>${t("rules.colFires")}</th>
      </tr></thead>
      <tbody>${rules.map((r) => html`<tr key=${r.id} class="row-link" onClick=${() => onOpen(r)}>
        <td class="sel" onClick=${(e) => e.stopPropagation()}>
          <input type="checkbox" aria-label=${t("rules.selectAria", { name: r.name })}
            checked=${selected.has(r.id)} onChange=${(e) => onSelect([r.id], e.target.checked)} /></td>
        <td><button class="link-btn" onClick=${(e) => { e.stopPropagation(); onOpen(r); }}
              aria-label=${t("rules.editAria", { name: r.name })}><b>${r.name}</b></button>
          ${r.inhibited_by?.length ? html` <span class="muted small" title=${r.inhibited_by.join(", ")}>⊘${r.inhibited_by.length}</span>` : null}
          ${r.trigger_summary ? html`<div class="muted small">${r.trigger_summary}</div>` : null}</td>
        <td class="mono small">${r.template_type}</td>
        <td><${RuleStatusBadge} rule=${r} /></td>
        <td class="small">${r.persist_n}× / ${r.eval_interval_sec}s</td>
        <td title=${fmtDateTime(r.last_fired_at)}>${r.last_fired_at ? fmtRelative(r.last_fired_at) : "—"}</td>
        <td class="num">${r.fire_count_lifetime}</td>
      </tr>`)}</tbody></table></div>` : null}
  </section>`;
}

const EMPTY_R = {
  template_type: "", condition_expr: "", persist_n: 1, eval_interval_sec: 10,
  incident_enabled: false, recovery_expr: "", recovery_persist_n: 1, resolved_template_type: "",
  vars_extract: [], inhibited_by: [], trigger_summary: "", trigger_logic_md: "",
  enabled: true, sort_order: 100,
};

function RuleEditor({ rule, templateRows = [], variables, rules, onClose, onSaved, onDuplicate }) {
  const isNew = !!rule.__new;
  const [name, setName] = useState(rule.name || "");
  // A11: stripMeta on a bare {__new:true} yields undefined for every field,
  // which would overwrite the EMPTY_R defaults (Number(undefined) → NaN →
  // 422 on submit). Merge only the DEFINED values so defaults survive.
  const [r, setR] = useState(isNew
    ? { ...EMPTY_R, ...Object.fromEntries(Object.entries(stripMeta(rule)).filter(([, v]) => v !== undefined)) }
    : { ...rule });
  const [validation, setValidation] = useState(null);
  const [recValidation, setRecValidation] = useState(null);
  const [evalRes, setEvalRes] = useState(null);
  const [fireRes, setFireRes] = useState(null);
  const [ctxText, setCtxText] = useState("{}");
  const [busy, setBusy] = useState(false);
  const fieldErrs = useFieldErrors();
  const [confirmDel, setConfirmDel] = useState(false);
  const nameOk = /^[a-z][a-z0-9_-]*$/.test(name);

  function set(k, v) { setR((c) => ({ ...c, [k]: v })); }

  async function validateExpr(expr, setResult) {
    if (!(expr || "").trim()) return;
    try { setResult(await api.post("/v1/rules/validate", { condition_expr: expr, vars_extract: r.vars_extract })); }
    catch (e) { toast.error(e); }
  }
  const validate = () => validateExpr(r.condition_expr, setValidation);

  async function save() {
    fieldErrs.clear();
    if (!fieldErrs.check([
      ["name", !isNew || nameOk, name ? t("rules.nameToastError") : null],
      ["template_type", (r.template_type || "").trim()],
      ["condition_expr", (r.condition_expr || "").trim()],
    ])) return;
    setBusy(true);
    try {
      const payload = {
        template_type: r.template_type, condition_expr: r.condition_expr,
        incident_enabled: !!r.incident_enabled, recovery_expr: r.recovery_expr || null,
        recovery_persist_n: Number(r.recovery_persist_n || 1), resolved_template_type: r.resolved_template_type || null,
        persist_n: Number(r.persist_n), eval_interval_sec: Number(r.eval_interval_sec),
        vars_extract: r.vars_extract, inhibited_by: r.inhibited_by,
        trigger_summary: r.trigger_summary || null, trigger_logic_md: r.trigger_logic_md || null,
        enabled: r.enabled, sort_order: Number(r.sort_order),
      };
      if (isNew) await api.post("/v1/rules", { name, ...payload });
      else await api.patch(`/v1/rules/${rule.id}`, payload);
      toast.ok(isNew ? t("rules.toastCreated") : t("rules.toastSaved"));
      draft.clear();
      onSaved();
    } catch (e) { if (!fieldErrs.show(e)) toast.error(e); } finally { setBusy(false); }
  }

  async function evalNow() {
    setEvalRes(null);
    try { setEvalRes(await api.post(`/v1/rules/${rule.id}/eval-now`)); } catch (e) { toast.error(e); }
  }
  async function testFire() {
    let ctx; try { ctx = JSON.parse(ctxText || "{}"); } catch { return toast.error(t("rules.toastInvalidJson")); }
    setFireRes(null);
    try { setFireRes(await api.post(`/v1/rules/${rule.id}/test`, { context: ctx })); } catch (e) { toast.error(e); }
  }
  function duplicate() {
    draft.clear();
    onDuplicate({ __new: true, ...stripMeta(r), name: (rule.name || "rule") + "-copy" });
  }
  async function doDelete() {
    setBusy(true);
    try { await api.del(`/v1/rules/${rule.id}`); toast.ok(t("rules.toastDeleted")); draft.clear(); onSaved(); }
    catch (e) { toast.error(e); setConfirmDel(false); } finally { setBusy(false); }
  }

  const dirty = useDirty({ name, r });
  const draft = useDraft("rules", isNew ? null : rule.id, { name, r }, dirty);
  const restoreDraft = () => { const d = draft.recovered; setName(d.name); setR(d.r); draft.restore(); };
  const closeDraft = () => { draft.clear(); onClose(); };
  // Templates as "icon type — severity", plus the current value if it is not
  // (or no longer) a template, so an existing rule never loses its setting.
  const tmplOptions = templateRows.map((tt) => ({ type: tt.type, label: `${tt.icon ? tt.icon + " " : ""}${tt.type} — ${sevLabel(tt.severity)}` }))
    .sort((a, b) => a.type.localeCompare(b.type));
  if (r.template_type && !tmplOptions.some((o) => o.type === r.template_type)) {
    tmplOptions.unshift({ type: r.template_type, label: `${r.template_type} — ${t("rules.missingTemplate")}` });
  }
  // The recovery template: same list, keeping a value that is not a template
  // (any more) so a save never drops it silently (review RL-10).
  const resolvedOptions = tmplOptions.filter((o) => templateRows.some((tt) => tt.type === o.type));
  if (r.resolved_template_type && !resolvedOptions.some((o) => o.type === r.resolved_template_type)) {
    resolvedOptions.unshift({ type: r.resolved_template_type, label: `${r.resolved_template_type} — ${t("rules.missingTemplate")}` });
  }
  // Inhibitors that name no rule are ignored by the engine (review RL-11).
  // Only once the list of rules has loaded, or every name would look unknown.
  const unknownInhibitors = (rules || []).length ? (r.inhibited_by || []).filter((n) => !rules.includes(n)) : [];
  // How long after the condition starts holding the alert goes out (first
  // check counts), for the plain-language hint.
  const delaySec = (Math.max(1, Number(r.persist_n) || 1) - 1) * (Number(r.eval_interval_sec) || 0);
  // Advanced options open by themselves when the rule uses one or has an error there.
  const advancedOpen = !!((r.vars_extract || []).length || r.incident_enabled || (r.inhibited_by || []).length
    || Number(r.sort_order) !== 100 || ["recovery_expr", "recovery_persist_n", "resolved_template_type"].some((f) => fieldErrs.msgFor(f)));
  return html`<${Drawer} open=${true} width=${760} title=${isNew ? t("rules.newRule") : rule.name} onClose=${closeDraft} dirty=${dirty}>
      ${draft.recovered ? html`<${DraftBanner} onRestore=${restoreDraft} onDiscard=${draft.dismiss} />` : null}
      <${FieldErrorSummary} errors=${fieldErrs.errors}
        idFor=${(f) => ({ name: "r-name", template_type: "r-tmpl", condition_expr: "r-cond", persist_n: "r-persistn", eval_interval_sec: "r-evalint", recovery_expr: "r-recovery", recovery_persist_n: "r-recovery-n", resolved_template_type: "r-resolved-tmpl" }[f.split(".").pop()] || "r-cond")} />
    <div class="editor">
      ${isNew ? html`<div class="field"><label for="r-name">${t("rules.nameLabel")} <span class="req">*</span></label>
        <input id="r-name" value=${name} onInput=${(e) => setName(e.target.value)}
          aria-invalid=${(name && !nameOk) || !!fieldErrs.msgFor("name") || undefined}
          aria-describedby=${fieldErrs.msgFor("name") ? fieldErrorId("name") : undefined} placeholder=${t("rules.namePlaceholder")} />
        ${name && !nameOk ? html`<div class="error small">${t("rules.nameRule")}</div>` : null}
        ${fieldErrs.msgFor("name") ? html`<div id=${fieldErrorId("name")} class="error small" role="alert">${fieldErrs.msgFor("name")}</div>` : null}</div>`
        : html`<p class="muted small mono">${t("rules.idPrefix", { id: rule.id })}${rule.last_eval_error ? html` · <span class="warn-text">${rule.last_eval_error}</span>` : ""}</p>`}

      <div class=${"field" + (fieldErrs.msgFor("template_type") ? " has-error" : "")}><label for="r-tmpl">${t("rules.templateTypeLabel")} <span class="req">*</span></label>
        <select id="r-tmpl" value=${r.template_type} onChange=${(e) => set("template_type", e.target.value)}
          aria-invalid=${fieldErrs.msgFor("template_type") ? "true" : undefined}
          aria-describedby=${fieldErrs.msgFor("template_type") ? fieldErrorId("template_type") : "r-tmpl-help"}>
          <option value="">${t("rules.chooseTemplate")}</option>
          ${tmplOptions.map((o) => html`<option key=${o.type} value=${o.type}>${o.label}</option>`)}
        </select>
        <div id="r-tmpl-help" class="hint">${t("rules.templateHelp")} <a href="#/templates">${t("rules.manageTemplates")}</a></div>
        ${fieldErrs.msgFor("template_type") ? html`<div id=${fieldErrorId("template_type")} class="error small" role="alert">${fieldErrs.msgFor("template_type")}</div>` : null}</div>

      <div class=${"field" + (fieldErrs.msgFor("condition_expr") ? " has-error" : "")}><label for="r-cond">${t("rules.conditionLabel")} <span class="req">*</span></label>
        <${ExprInput} id="r-cond" rows="3" value=${r.condition_expr} variables=${variables}
          onChange=${(v) => { set("condition_expr", v); setValidation(null); }}
          aria-invalid=${fieldErrs.msgFor("condition_expr") ? "true" : undefined}
          aria-describedby=${fieldErrs.msgFor("condition_expr") ? fieldErrorId("condition_expr") : undefined}
          placeholder=${t("rules.conditionPlaceholder")} />
        ${fieldErrs.msgFor("condition_expr") ? html`<div id=${fieldErrorId("condition_expr")} class="error small" role="alert">${fieldErrs.msgFor("condition_expr")}</div>` : null}
        <div class="form-actions"><button type="button" class="btn sm" onClick=${validate}>${t("rules.validate")}</button>
        </div>
        <${ValidationResult} validation=${validation} />
      </div>

      <details class="cheat"><summary>${t("rules.cheatSheet")}</summary>
        <table class="tbl small">${cheatRows().map(([fn, d]) => html`<tr key=${fn}><td class="mono">${fn}</td><td class="muted">${d}</td></tr>`)}</table>
      </details>

      <fieldset class="timing">
        <legend>${t("rules.timingLegend")}</legend>
        <p class="timing-sentence">${t("rules.timingA")}
          <input id="r-persistn" type="number" min="1" class="inline-num" value=${r.persist_n} aria-label=${t("rules.persistN")}
            onInput=${(e) => set("persist_n", e.target.value)} ...${fieldErrs.attrs("persist_n")} />
          ${t("rules.timingB")}
          <input id="r-evalint" type="number" min="1" class="inline-num" value=${r.eval_interval_sec} aria-label=${t("rules.evalInterval")}
            onInput=${(e) => set("eval_interval_sec", e.target.value)} ...${fieldErrs.attrs("eval_interval_sec")} />
          ${t("rules.timingC")}</p>
        ${delaySec > 0 ? html`<p class="hint">${Number(r.persist_n) > 1 ? t("rules.timingDelay", { delay: fmtSeconds(delaySec) }) : t("rules.timingFirst")}</p>` : null}
      </fieldset>

      <div class="field"><label for="r-summary">${t("rules.triggerSummary")}</label><input id="r-summary" maxlength="500" value=${r.trigger_summary || ""} onInput=${(e) => set("trigger_summary", e.target.value)} /></div>
      <div class="field"><label for="r-logic">${t("rules.triggerLogic")}</label>
        <textarea id="r-logic" rows="4" value=${r.trigger_logic_md || ""} onInput=${(e) => set("trigger_logic_md", e.target.value)} aria-describedby="r-logic-help"></textarea>
        <p id="r-logic-help" class="muted small">${t("rules.triggerLogicHelp")}</p></div>
      <div class="field"><label class="chk"><input type="checkbox" checked=${r.enabled} onChange=${(e) => set("enabled", e.target.checked)} /> ${t("rules.enabled")}</label></div>

      <details class="advanced" open=${advancedOpen}>
      <summary>${t("rules.advanced")}</summary>
      <div class="field"><label for="r-vars">${t("rules.varsCapture")}</label>
        <${TagInput} inputId="r-vars" ariaLabel=${t("rules.varsCapture")} value=${r.vars_extract} onChange=${(v) => set("vars_extract", v)} options=${variables} placeholder=${t("rules.varNamePlaceholder")} />
        <p class="muted small">${t("rules.varsHelp")}</p></div>
      <div class="field"><label class="chk"><input type="checkbox" checked=${!!r.incident_enabled} onChange=${(e) => set("incident_enabled", e.target.checked)} /> ${t("rules.incidentEnabled")}</label>
        <p class="muted small">${t("rules.incidentHelp")}</p></div>
      ${r.incident_enabled ? html`
        <div class="field"><label for="r-recovery">${t("rules.recoveryExpr")}</label>
          <${ExprInput} id="r-recovery" rows="2" value=${r.recovery_expr || ""} variables=${variables}
            onChange=${(v) => { set("recovery_expr", v); setRecValidation(null); }} placeholder="x < 75"
            aria-invalid=${!!fieldErrs.msgFor("recovery_expr") || undefined}
            aria-describedby=${fieldErrs.msgFor("recovery_expr") ? fieldErrorId("recovery_expr") : "r-recovery-help"} />
          ${fieldErrs.msgFor("recovery_expr") ? html`<div class="error small" id=${fieldErrorId("recovery_expr")} role="alert">${fieldErrs.msgFor("recovery_expr")}</div>` : null}
          ${(r.recovery_expr || "").trim() ? html`<div class="form-actions"><button type="button" class="btn sm" onClick=${() => validateExpr(r.recovery_expr, setRecValidation)}>${t("rules.validate")}</button></div>
            <${ValidationResult} validation=${recValidation} />` : null}
          <p id="r-recovery-help" class="muted small">${t("rules.recoveryHelp")}</p></div>
        <div class="field"><label for="r-recovery-n">${t("rules.recoveryPersist")}</label>
          <input id="r-recovery-n" type="number" min="1" max="10000" value=${r.recovery_persist_n || 1} onInput=${(e) => set("recovery_persist_n", e.target.value)} /></div>
        <div class="field"><label for="r-resolved-tmpl">${t("rules.resolvedTemplate")}</label>
          <select id="r-resolved-tmpl" value=${r.resolved_template_type || ""} onChange=${(e) => set("resolved_template_type", e.target.value)} aria-describedby="r-resolved-help">
            <option value="">${t("rules.resolvedSilent")}</option>
            ${resolvedOptions.map((o) => html`<option key=${o.type} value=${o.type}>${o.label}</option>`)}
          </select>
          <p id="r-resolved-help" class="muted small">${t("rules.resolvedTemplateHelp")}</p></div>
      ` : null}
      <div class="field"><label for="r-inhib">${t("rules.inhibitedBy")}</label>
        <${TagInput} inputId="r-inhib" ariaLabel=${t("rules.inhibitedByAria")} value=${r.inhibited_by} onChange=${(v) => set("inhibited_by", v)} options=${rules} placeholder=${t("rules.ruleNamePlaceholder")} />
        ${unknownInhibitors.length ? html`<div class="small warn-text" role="status">${t("rules.unknownInhibitors", { names: unknownInhibitors.join(", ") })}</div>` : null}</div>

      <div class="field"><label for="r-sort">${t("rules.sortOrder")}</label><input id="r-sort" type="number" value=${r.sort_order} onInput=${(e) => set("sort_order", e.target.value)} /></div>
      </details>

      <div class="editor-actions">
        <button class="btn primary" onClick=${save} disabled=${busy}>${isNew ? t("rules.create") : t("rules.save")}</button>
        ${!isNew ? html`
          <button class="btn" onClick=${evalNow} disabled=${busy}>${t("rules.evalNow")}</button>
          <button class="btn" onClick=${duplicate} disabled=${busy}>${t("rules.duplicate")}</button>
          <a class="btn" href=${`#/log?rule=${rule.id}`} onClick=${onClose}>${t("rules.history")}</a>
          <span class="spacer"></span>
          <button class="btn danger" onClick=${() => setConfirmDel(true)} disabled=${busy}>${t("rules.delete")}</button>` : null}
      </div>

      ${!isNew ? html`<div class="field" style="margin-top:12px"><label for="r-testctx">${t("rules.testContextLabel")}</label>
        <textarea id="r-testctx" rows="2" class="mono" value=${ctxText} onInput=${(e) => setCtxText(e.target.value)}></textarea>
        <div class="form-actions"><button class="btn sm" onClick=${testFire}>${t("rules.testFire")}</button></div></div>` : null}

      ${evalRes ? html`<div class="result"><b>${t("rules.evalNowResult")}</b> ${evalRes.matched ? html`<span class="badge ok plain">${t("rules.matched")}</span>` : html`<span class="badge plain">${t("rules.noMatch")}</span>`}
        ${evalRes.error ? html`<span class="error small">${evalRes.error}</span>` : null}
        <div class="small muted">${t("rules.consecutiveMatches", { count: evalRes.consecutive_match_count })}</div><${Json} value=${evalRes.context} /></div>` : null}
      ${fireRes ? html`<div class="result"><b>${t("rules.firedResult")}</b> ${fireRes.dispatched ? html`<span class="badge ok plain">${t("rules.dispatched")}</span>` : html`<span class="badge warning plain">${fireRes.suppressed_reason || t("rules.notDispatched")}</span>`}<${Json} value=${fireRes} /></div>` : null}

      <${KindHelp} help=${tnode("rules.help")} />
    </div>

    <${DangerConfirm} open=${confirmDel} token=${rule.name} title=${t("rules.deleteTitle", { name: rule.name })} busy=${busy}
      onConfirm=${doDelete} onClose=${() => setConfirmDel(false)} />
  </${Drawer}>`;
}

// Keep only editable rule fields (drop id/timestamps/runtime counters).
function stripMeta(r) {
  const { template_type, condition_expr, persist_n, eval_interval_sec, vars_extract,
    inhibited_by, trigger_summary, trigger_logic_md, enabled, sort_order,
    incident_enabled, recovery_expr, recovery_persist_n, resolved_template_type } = r;
  return { template_type, condition_expr, persist_n, eval_interval_sec,
    incident_enabled, recovery_expr, recovery_persist_n, resolved_template_type,
    vars_extract: vars_extract || [], inhibited_by: inhibited_by || [],
    trigger_summary, trigger_logic_md, enabled, sort_order };
}
