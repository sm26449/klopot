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

// Persistence as a duration (review RL-30). The API keeps persist_n (checks
// in a row, the first one counts): "held for at least D" = ceil(D / interval)
// + 1, so the alert never goes out sooner than asked (review RV-06: rounding
// down made 5 s at a 10 s interval "at the first check").
const UNITS = [["h", 3600], ["min", 60], ["s", 1]];
export const MAX_CHECKS = 10000;
export function holdToChecks(holdSec, intervalSec) {
  const s = Math.max(1, Number(intervalSec) || 1);
  return Math.min(MAX_CHECKS, Math.ceil(Math.max(0, Number(holdSec) || 0) / s) + 1);
}
export function checksToHold(n, intervalSec) {
  return (Math.max(1, Number(n) || 1) - 1) * Math.max(1, Number(intervalSec) || 1);
}
/** [value, unit] in the largest unit that divides ``sec`` (0 → [0, "min"]). */
export function splitDuration(sec) {
  if (!sec) return [0, "min"];
  const [unit, size] = UNITS.find(([, n]) => sec % n === 0);
  return [sec / size, unit];
}
/** For a plain threshold (``x > 80``) a recovery with a 5 % band
 *  (``x < 76``), so a value hovering at the threshold does not open and close
 *  the incident on every check (review RL-33). Null for anything else. */
export function hysteresisFor(cond) {
  const m = /^\s*([A-Za-z_][\w.]*)\s*(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)\s*$/.exec(cond || "");
  if (!m) return null;
  const [, name, op, raw] = m;
  const x = Number(raw);
  const band = Math.abs(x) * 0.05 || 1;
  const decimals = (raw.split(".")[1] || "").length;
  const round = (v) => Number(v.toFixed(Math.max(decimals, band < 1 ? 1 : 0)));
  return op.startsWith(">") ? `${name} < ${round(x - band)}` : `${name} > ${round(x + band)}`;
}
const unitSec = (unit) => (UNITS.find(([u]) => u === unit) || UNITS[2])[1];

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
const runSince = (r) => (r.run_state_since ? t("rules.stateSince", { when: fmtDateTime(r.run_state_since) }) : "");

export function RuleStatusBadge({ rule: r }) {
  if (!r.enabled) {
    return r.eval_status === "ok"
      ? html`<span class="badge plain">${t("rules.badgeOff")}</span>`
      : html`<span class="badge plain" title=${t("rules.disabledLastErrorTitle", { error: r.last_eval_error || "" })}>${t("rules.badgeOffLastError")}</span>`;
  }
  if (r.eval_status === "error") return html`<span class="badge warning plain" title=${r.last_eval_error || ""}>${t("rules.badgeError")}</span>`;
  if (r.eval_status === "no_data") return html`<span class="badge plain" title=${r.last_eval_error || ""}>${t("rules.badgeNoData")}</span>`;
  // Where the rule is in its cycle (review RL-32).
  if (r.run_state === "firing") return html`<span class="badge critical plain" title=${runSince(r)}>${t("rules.badgeFiring")}</span>`;
  if (r.run_state === "pending") return html`<span class="badge warning plain" title=${runSince(r)}>${t("rules.badgePending")}</span>`;
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
/** The template types a rule's ``type`` stands for: itself, or one per
 *  ``for_each`` value when it holds the ``{param}`` placeholder (ADR-0005). */
export function expandedTypes(type, forEach) {
  const [param, values] = forEachParts(forEach);
  if (!type || !values.length || !type.includes(`{${param}}`)) return type ? [type] : [];
  return values.map((v) => type.split(`{${param}}`).join(v));
}

export function groupRules(rules, templateRows) {
  const labels = categoryLabels(templateRows);
  const categoryOf = new Map(templateRows.map((tt) => [tt.type, tt.category]));
  const none = t("rules.uncategorized");
  const groups = new Map();
  for (const r of rules) {
    // A parametric rule takes its category from its instances' templates (RC-09).
    const c = expandedTypes(r.template_type, r.for_each).map((x) => categoryOf.get(x)).find(Boolean);
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
        <th>${t("rules.colPersist")}</th><th>${t("rules.colLastTrue")}</th><th>${t("rules.colLastFired")}</th><th>${t("rules.colFires")}</th>
      </tr></thead>
      <tbody>${rules.map((r) => html`<tr key=${r.id} class="row-link" onClick=${() => onOpen(r)}>
        <td class="sel" onClick=${(e) => e.stopPropagation()}>
          <input type="checkbox" aria-label=${t("rules.selectAria", { name: r.name })}
            checked=${selected.has(r.id)} onChange=${(e) => onSelect([r.id], e.target.checked)} /></td>
        <td><button class="link-btn" onClick=${(e) => { e.stopPropagation(); onOpen(r); }}
              aria-label=${t("rules.editAria", { name: r.name })}><b>${r.name}</b></button>
          ${r.inhibited_by?.length ? html` <span class="muted small" title=${r.inhibited_by.join(", ")}>⊘${r.inhibited_by.length}</span>` : null}
          ${r.for_each ? html` <span class="chip small" title=${forEachParts(r.for_each)[1].join(", ")}>×${forEachParts(r.for_each)[1].length}</span>` : null}
          ${r.trigger_summary ? html`<div class="muted small">${r.trigger_summary}</div>` : null}</td>
        <td class="mono small">${r.template_type}</td>
        <td><${RuleStatusBadge} rule=${r} /></td>
        <td class="small">${r.persist_n}× / ${r.eval_interval_sec}s</td>
        <td title=${fmtDateTime(r.last_true_at)}>${r.last_true_at ? fmtRelative(r.last_true_at) : "—"}</td>
        <td title=${fmtDateTime(r.last_fired_at)}>${r.last_fired_at ? fmtRelative(r.last_fired_at) : "—"}</td>
        <td class="num">${r.fire_count_lifetime}</td>
      </tr>`)}</tbody></table></div>` : null}
  </section>`;
}

const EMPTY_R = {
  template_type: "", condition_expr: "", persist_n: 1, eval_interval_sec: 10,
  incident_enabled: false, recovery_expr: "", recovery_persist_n: 1, resolved_template_type: "",
  vars_extract: [], inhibited_by: [], trigger_summary: "", trigger_logic_md: "",
  enabled: true, sort_order: 100, for_each: null,
};

// The parameter and values of a parametric rule (ADR-0005): {"n": [...]}.
export function forEachParts(fe) {
  const [param, values] = Object.entries(fe || {})[0] || ["n", []];
  return [param, values || []];
}

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
  // "What if": the condition with other values (review RL-31).
  const [whatIfText, setWhatIfText] = useState(null);
  const [whatIf, setWhatIf] = useState(null);
  // Run-state history of a saved rule (review RL-32), and its instances (ADR-0005).
  const [history, setHistory] = useState(null);
  const [instanceRows, setInstanceRows] = useState(null);
  const [paramDraft, setParamDraft] = useState(() => forEachParts(rule.for_each)[0]);
  useEffect(() => {
    if (isNew) return;
    lookup(api.get(`/v1/rules/${rule.id}/transitions`, { limit: 50 }), []).then((rows) => setHistory(Array.isArray(rows) ? rows : []));
    if (rule.for_each) lookup(api.get(`/v1/rules/${rule.id}/instances`), []).then((rows) => setInstanceRows(Array.isArray(rows) ? rows : []));
  }, []);
  // How long the condition must hold, kept while the interval changes (RL-30).
  const [hold, setHold] = useState(() => splitDuration(checksToHold(rule.persist_n ?? 1, rule.eval_interval_sec ?? 10)));
  const [busy, setBusy] = useState(false);
  const fieldErrs = useFieldErrors();
  const [confirmDel, setConfirmDel] = useState(false);
  const nameOk = /^[a-z][a-z0-9_-]*$/.test(name);

  function set(k, v) { setR((c) => ({ ...c, [k]: v })); }

  async function validateExpr(expr, setResult) {
    if (!(expr || "").trim()) return;
    try { setResult(await api.post("/v1/rules/validate", { condition_expr: expr, vars_extract: r.vars_extract, for_each: r.for_each || null })); }
    catch (e) { toast.error(e); }
  }
  const validate = () => { setWhatIf(null); setWhatIfText(null); validateExpr(r.condition_expr, setValidation); };
  // Start from the live values the validation reported (missing ones null).
  function openWhatIf() {
    const values = Object.fromEntries((validation?.referenced_vars || []).map((v) => [v.name, v.present ? v.live_value : null]));
    setWhatIfText(JSON.stringify(values, null, 2));
    setWhatIf(null);
  }
  async function runWhatIf() {
    let context; try { context = JSON.parse(whatIfText || "{}"); } catch { return toast.error(t("rules.toastInvalidJson")); }
    if (!context || typeof context !== "object" || Array.isArray(context)) return toast.error(t("rules.toastInvalidJson"));
    try { setWhatIf(await api.post("/v1/rules/validate", { condition_expr: r.condition_expr, vars_extract: r.vars_extract, for_each: r.for_each || null, context })); }
    catch (e) { toast.error(e); }
  }
  // The parameter's name is kept while there are no values yet.
  const feValues = forEachParts(r.for_each)[1];
  const feParam = r.for_each ? forEachParts(r.for_each)[0] : paramDraft;
  // The parameter must appear somewhere, or every instance is the same rule.
  const usesParam = [r.condition_expr, r.recovery_expr, r.template_type, r.resolved_template_type, ...(r.vars_extract || [])]
    .some((x) => (x || "").includes(`{${feParam}}`));
  function setForEach(param, values) {
    setParamDraft(param);
    set("for_each", values.length ? { [param || "n"]: values } : null);
  }
  function setHoldPart(value, unit) {
    setHold([value, unit]);
    set("persist_n", holdToChecks(Number(value) * unitSec(unit), r.eval_interval_sec));
  }
  function setInterval_(v) {
    set("eval_interval_sec", v);
    set("persist_n", holdToChecks(Number(hold[0]) * unitSec(hold[1]), v));
  }

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
        vars_extract: r.vars_extract, inhibited_by: r.inhibited_by, for_each: r.for_each || null,
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
  // The duration follows the restored rule, or a later interval change would
  // recompute persist_n from the saved one (review RV-01).
  const restoreDraft = () => {
    const d = draft.recovered;
    setName(d.name); setR(d.r);
    setHold(splitDuration(checksToHold(d.r.persist_n, d.r.eval_interval_sec)));
    draft.restore();
  };
  const closeDraft = () => { draft.clear(); onClose(); };
  // Templates as "icon type — severity", plus the current value if it is not
  // (or no longer) a template, so an existing rule never loses its setting.
  const tmplOptions = templateRows.map((tt) => ({ type: tt.type, label: `${tt.icon ? tt.icon + " " : ""}${tt.type} — ${sevLabel(tt.severity)}` }))
    .sort((a, b) => a.type.localeCompare(b.type));
  // A parametric type (ov_active_{n}) is valid when every instance's
  // template exists — never offer to create the literal pattern (RC-09).
  const templateNote = (type) => {
    const types = expandedTypes(type, r.for_each);
    if (types.length > 1 || (types[0] !== type && types.length)) {
      const missing = types.filter((x) => !templateRows.some((tt) => tt.type === x));
      return missing.length ? t("rules.patternMissing", { missing: missing.join(", ") })
        : t("rules.patternOk", { types: types.join(", ") });
    }
    return t("rules.missingTemplate");
  };
  if (r.template_type && !tmplOptions.some((o) => o.type === r.template_type)) {
    tmplOptions.unshift({ type: r.template_type, label: `${r.template_type} — ${templateNote(r.template_type)}` });
  }
  // The recovery template: same list, keeping a value that is not a template
  // (any more) so a save never drops it silently (review RL-10).
  const resolvedOptions = tmplOptions.filter((o) => templateRows.some((tt) => tt.type === o.type));
  if (r.resolved_template_type && !resolvedOptions.some((o) => o.type === r.resolved_template_type)) {
    resolvedOptions.unshift({ type: r.resolved_template_type, label: `${r.resolved_template_type} — ${templateNote(r.resolved_template_type)}` });
  }
  // Inhibitors that name no rule are ignored by the engine (review RL-11).
  // Only once the list of rules has loaded, or every name would look unknown.
  const unknownInhibitors = (rules || []).length ? (r.inhibited_by || []).filter((n) => !rules.includes(n)) : [];
  // How long after the condition starts holding the alert goes out (first
  // check counts), for the plain-language hint.
  const delaySec = (Math.max(1, Number(r.persist_n) || 1) - 1) * (Number(r.eval_interval_sec) || 0);
  // Advanced options open by themselves when the rule uses one or has an error there.
  const advancedOpen = !!((r.vars_extract || []).length || r.incident_enabled || (r.inhibited_by || []).length || r.for_each
    || Number(r.sort_order) !== 100 || ["recovery_expr", "recovery_persist_n", "resolved_template_type"].some((f) => fieldErrs.msgFor(f)));
  return html`<${Drawer} open=${true} width=${760} title=${isNew ? t("rules.newRule") : rule.name} onClose=${closeDraft} dirty=${dirty}>
      ${draft.recovered ? html`<${DraftBanner} onRestore=${restoreDraft} onDiscard=${draft.dismiss} />` : null}
      <${FieldErrorSummary} errors=${fieldErrs.errors}
        idFor=${(f) => ({ name: "r-name", template_type: "r-tmpl", condition_expr: "r-cond", persist_n: "r-hold", eval_interval_sec: "r-evalint", recovery_expr: "r-recovery", recovery_persist_n: "r-recovery-n", resolved_template_type: "r-resolved-tmpl" }[f.split(".").pop()] || "r-cond")} />
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
          ${validation?.referenced_vars?.length && whatIfText === null ? html`<button type="button" class="btn sm" onClick=${openWhatIf}>${t("rules.whatIfOpen")}</button>` : null}
        </div>
        <${ValidationResult} validation=${validation} />
        ${whatIfText !== null ? html`<div class="what-if">
          <label for="r-whatif">${t("rules.whatIfLabel")}</label>
          <textarea id="r-whatif" class="mono" rows=${Math.min(8, whatIfText.split("\n").length)} value=${whatIfText}
            onInput=${(e) => { setWhatIfText(e.target.value); setWhatIf(null); }} aria-describedby="r-whatif-help" spellcheck="false"></textarea>
          <p id="r-whatif-help" class="muted small">${t("rules.whatIfHelp")}</p>
          <div class="form-actions"><button type="button" class="btn sm" onClick=${runWhatIf}>${t("rules.whatIfRun")}</button></div>
          <${ValidationResult} validation=${whatIf} />
        </div>` : null}
      </div>

      <details class="cheat"><summary>${t("rules.cheatSheet")}</summary>
        <table class="tbl small">${cheatRows().map(([fn, d]) => html`<tr key=${fn}><td class="mono">${fn}</td><td class="muted">${d}</td></tr>`)}</table>
      </details>

      <fieldset class="timing">
        <legend>${t("rules.timingLegend")}</legend>
        <p class="timing-sentence">${t("rules.timingHoldA")}
          <input id="r-hold" type="number" min="0" class="inline-num" value=${hold[0]} aria-label=${t("rules.holdFor")}
            onInput=${(e) => setHoldPart(e.target.value, hold[1])} ...${fieldErrs.attrs("persist_n")} />
          <select id="r-hold-unit" class="inline-num" value=${hold[1]} aria-label=${t("rules.holdUnit")}
            onChange=${(e) => setHoldPart(hold[0], e.target.value)}>
            ${UNITS.map(([u]) => html`<option key=${u} value=${u}>${t("rules.unit_" + u)}</option>`)}</select>
          ${t("rules.timingHoldB")}
          <input id="r-evalint" type="number" min="1" class="inline-num" value=${r.eval_interval_sec} aria-label=${t("rules.evalInterval")}
            onInput=${(e) => setInterval_(e.target.value)} ...${fieldErrs.attrs("eval_interval_sec")} />
          ${t("rules.timingC")}</p>
        <p class="hint">${Number(r.persist_n) > 1 ? t("rules.timingChecks", { count: r.persist_n, delay: fmtSeconds(delaySec) }) : t("rules.timingFirst")}
          ${Number(r.persist_n) >= MAX_CHECKS ? html` <span class="warn-text">${t("rules.timingCapped", { max: MAX_CHECKS })}</span>`
            : Number(hold[0]) * unitSec(hold[1]) !== delaySec ? html` <span class="warn-text">${t("rules.timingRounded", { delay: fmtSeconds(delaySec) })}</span>` : null}</p>
      </fieldset>

      <div class="field"><label for="r-summary">${t("rules.triggerSummary")}</label><input id="r-summary" maxlength="500" value=${r.trigger_summary || ""} onInput=${(e) => set("trigger_summary", e.target.value)} /></div>
      <div class="field"><label for="r-logic">${t("rules.triggerLogic")}</label>
        <textarea id="r-logic" rows="4" value=${r.trigger_logic_md || ""} onInput=${(e) => set("trigger_logic_md", e.target.value)} aria-describedby="r-logic-help"></textarea>
        <p id="r-logic-help" class="muted small">${t("rules.triggerLogicHelp")}</p></div>
      <div class="field"><label class="chk"><input type="checkbox" checked=${r.enabled} onChange=${(e) => set("enabled", e.target.checked)} /> ${t("rules.enabled")}</label></div>

      <details class="advanced" open=${advancedOpen}>
      <summary>${t("rules.advanced")}</summary>
      <fieldset class="for-each"><legend>${t("rules.forEach")}</legend>
        <p class="timing-sentence">${t("rules.forEachA")}
          <input id="r-fe-param" class="inline-num mono" value=${feParam} aria-label=${t("rules.forEachParam")} maxlength="32"
            onInput=${(e) => setForEach(e.target.value, feValues)} />
          ${t("rules.forEachB")}</p>
        <${TagInput} inputId="r-fe-values" ariaLabel=${t("rules.forEachValues")} value=${feValues}
          onChange=${(v) => setForEach(feParam, v)} placeholder=${t("rules.forEachValuesPlaceholder")} />
        <p class="muted small">${t("rules.forEachHelp", { param: `{${feParam || "n"}}` })}</p>
        ${feValues.length && !usesParam ? html`<p class="warn-text small">${t("rules.forEachUnused", { param: `{${feParam}}` })}</p>` : null}
      </fieldset>
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
          ${!(r.recovery_expr || "").trim() && hysteresisFor(r.condition_expr) ? html`<div class="form-actions">
            <button type="button" class="btn sm" onClick=${() => set("recovery_expr", hysteresisFor(r.condition_expr))}>
              ${t("rules.recoverySuggest", { expr: hysteresisFor(r.condition_expr) })}</button></div>` : null}
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

      ${instanceRows?.length ? html`<details class="history" open><summary>${t("rules.instancesTitle", { count: instanceRows.length })}</summary>
        <table class="tbl small"><thead><tr><th>${t("rules.instanceCol")}</th><th>${t("rules.colState")}</th><th>${t("rules.colLastTrue")}</th><th>${t("rules.historyDetail")}</th></tr></thead>
          <tbody>${instanceRows.map((i) => html`<tr key=${i.instance}>
            <td class="mono">${i.instance}</td>
            <td>${i.run_state ? t("rules.state_" + i.run_state) : "—"}</td>
            <td title=${fmtDateTime(i.last_true_at)}>${i.last_true_at ? fmtRelative(i.last_true_at) : "—"}</td>
            <td class="muted small">${i.last_eval_error || ""}</td></tr>`)}</tbody></table>
      </details>` : null}

      ${!isNew ? html`<details class="history"><summary>${t("rules.historyTitle")}${rule.run_state ? html` · <span class="muted">${t("rules.state_" + rule.run_state)}</span>` : null}</summary>
        ${history === null ? html`<p class="muted small">${t("common.loading")}</p>`
          : history.length === 0 ? html`<p class="muted small">${t("rules.historyEmpty")}</p>`
          : html`<table class="tbl small"><thead><tr><th>${t("rules.historyWhen")}</th><th>${t("rules.historyChange")}</th><th>${t("rules.historyDetail")}</th></tr></thead>
            <tbody>${history.map((h, i) => html`<tr key=${i}>
              <td title=${fmtDateTime(h.at)}>${fmtRelative(h.at)}</td>
              <td>${h.instance ? html`<span class="mono">${h.instance}</span> · ` : null}${h.from_state ? t("rules.state_" + h.from_state) + " → " : ""}<b>${t("rules.state_" + h.to_state)}</b></td>
              <td class="muted small">${h.detail || ""}</td></tr>`)}</tbody></table>`}
        <p class="muted small">${t("rules.historyHelp")}</p>
      </details>` : null}

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
    incident_enabled, recovery_expr, recovery_persist_n, resolved_template_type, for_each } = r;
  return { template_type, condition_expr, persist_n, eval_interval_sec,
    incident_enabled, recovery_expr, recovery_persist_n, resolved_template_type,
    vars_extract: vars_extract || [], inhibited_by: inhibited_by || [],
    trigger_summary, trigger_logic_md, enabled, sort_order, for_each: for_each || null };
}
