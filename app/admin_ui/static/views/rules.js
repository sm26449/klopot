// Rules (phase F6): table + editor with live validation, an expression
// cheat-sheet, eval-now, test fire, duplicate and typed-confirm delete.
import { html, useState, useEffect } from "../lib/h.js";
import { clickable } from "../lib/a11y.js";
import { useLoader } from "../lib/loader.js";
import { api } from "../lib/api.js";
import { navigate, useUrlFilters } from "../lib/router.js";
import { toast } from "../lib/toast.js";
import { Drawer, useDirty, Spinner, Empty, ErrorState, StaleBanner, Pager, DangerConfirm, Json, KindHelp, DraftBanner } from "../lib/ui.js";
import { useDraft } from "../lib/draft.js";
import { TagInput, useFieldErrors, FieldErrorSummary, fieldErrorId } from "../lib/form.js";
import { fmtRelative, fmtDateTime } from "../lib/format.js";
import { t, tnode } from "../lib/i18n.js";

const LIMIT = 50;
// Expression cheat-sheet rows: [signature, human description]. Built at render
// time so the translated descriptions re-resolve when the language changes.
function cheats() {
  return [
    ["var_age(\"name\")", t("rules.cheatVarAge")],
    ["clamp(x, lo, hi)", t("rules.cheatClamp")],
    ["avg([a, b, …])", t("rules.cheatAvg")],
    ["contains(s, sub)", t("rules.cheatContains")],
    ["regex_match(s, pat)", t("rules.cheatRegex")],
    ["in_window(start_h, end_h)", t("rules.cheatInWindow")],
    ["hour_now() / dow_now()", t("rules.cheatHourNow")],
    ["abs min max round sum len", t("rules.cheatNumeric")],
    ["AND OR NOT", t("rules.cheatBoolean")],
  ];
}

export function RulesView({ query, params }) {
  // Filters AND the page offset live in the URL so they survive reload/back/
  // forward and deep-links, and any filter change resets to page 1 (UX-015/R5).
  const [filters, setF, , offset, setOffset] = useUrlFilters("/rules", query, { template_type: "", enabled: "", has_error: "", search: "" });
  const [templates, setTemplates] = useState([]);
  const [variables, setVariables] = useState([]);
  const [allRules, setAllRules] = useState([]);
  const [editing, setEditing] = useState(null);

  // Deep-link (/rules/:id, e.g. from an alert's "rule #N"): open that rule,
  // fetching it even if it isn't on the current page; a missing id falls back
  // to the list with a message (UX-014).
  useEffect(() => {
    const id = params && params.id;
    if (!id) return undefined;
    let active = true;
    api.get(`/v1/rules/${encodeURIComponent(id)}`)
      .then((r) => { if (active) setEditing(r); })
      .catch(() => { if (active) { toast.error(t("rules.notFound", { id })); navigate("/rules"); } });
    return () => { active = false; };
  }, [params && params.id]);
  // force: the Drawer's dirty guard already confirmed, so don't re-ask here.
  const closeEditor = () => { setEditing(null); if (params && params.id) navigate("/rules", null, { force: true }); };

  // Debounced + cancelable load with a stale-response guard (audit A28).
  const [data, , reload, error] = useLoader((signal) => {
    const q = { skip: offset, limit: LIMIT };
    if (filters.template_type) q.template_type = filters.template_type;
    if (filters.enabled) q.enabled = filters.enabled;
    if (filters.has_error) q.has_error = filters.has_error;
    if (filters.search) q.search = filters.search;
    return api.get("/v1/rules", q, { signal });
  }, [filters, offset]);

  useEffect(() => {
    api.get("/v1/templates", { limit: 500 }).then((p) => setTemplates(p.items.map((t) => t.type).sort())).catch(() => {});
    api.get("/v1/variables", { limit: 500 }).then((p) => setVariables(p.items.map((v) => v.name).sort())).catch(() => {});
    api.get("/v1/rules", { limit: 500 }).then((p) => setAllRules(p.items.map((r) => r.name).sort())).catch(() => {});
  }, []);

  const items = data?.items || [];
  // Only an ENABLED rule that is erroring is a current incident. A disabled
  // rule keeps its last eval error as history (consecutive_eval_errors frozen),
  // which must not be surfaced as something failing now (audit V21).
  const broken = items.filter((r) => r.enabled && (r.consecutive_eval_errors > 0 || r.last_eval_error));

  return html`<div>
    <div class="page-head">
      <div><h1>${t("rules.title")}</h1><p class="muted">${t("rules.subtitle")}</p></div>
      <div class="actions"><button class="btn primary" onClick=${() => setEditing({ __new: true })}>${t("rules.newRule")}</button></div>
    </div>

    ${broken.length ? html`<div class="alert warn"><b>${t("rules.evalErrorsBanner", { count: broken.length })}</b>
      ${broken.slice(0, 3).map((r) => html`<span key=${r.id} class="mono small"> ${r.name}</span>`)}${broken.length > 3 ? "…" : ""}</div>` : null}

    <div class="card filters">
      <input class="grow" aria-label=${t("rules.searchAria")} placeholder=${t("rules.searchPlaceholder")} value=${filters.search} onInput=${(e) => setF("search", e.target.value)} />
      <select aria-label=${t("rules.filterTemplateAria")} value=${filters.template_type} onChange=${(e) => setF("template_type", e.target.value)}>
        <option value="">${t("rules.anyTemplate")}</option>${templates.map((tt) => html`<option key=${tt} value=${tt}>${tt}</option>`)}</select>
      <select aria-label=${t("rules.filterStateAria")} value=${filters.enabled} onChange=${(e) => setF("enabled", e.target.value)}>
        <option value="">${t("rules.anyState")}</option><option value="true">${t("rules.enabled")}</option><option value="false">${t("rules.disabled")}</option></select>
      <select aria-label=${t("rules.filterErrorAria")} value=${filters.has_error} onChange=${(e) => setF("has_error", e.target.value)}>
        <option value="">${t("rules.all")}</option><option value="true">${t("rules.withErrors")}</option></select>
    </div>

    ${error && data ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    <div class="card" style="margin-top:14px; padding:0">
      ${error && !data ? html`<${ErrorState} error=${error} onRetry=${reload} />` : data === null ? html`<${Spinner} />` : items.length === 0 ? html`<${Empty} label=${t("rules.empty")} />`
        : html`<table class="tbl"><thead><tr><th>${t("rules.colName")}</th><th>${t("rules.colTemplate")}</th><th>${t("rules.colState")}</th><th>${t("rules.colPersist")}</th><th>${t("rules.colLastFired")}</th><th>${t("rules.colFires")}</th></tr></thead>
          <tbody>${items.map((r) => html`<tr key=${r.id} ...${clickable(() => setEditing(r), t("rules.editAria", { name: r.name }))} style="cursor:pointer">
            <td><b>${r.name}</b>${r.inhibited_by?.length ? html` <span class="muted small">⊘${r.inhibited_by.length}</span>` : null}</td>
            <td class="mono small">${r.template_type}</td>
            <td>${(r.consecutive_eval_errors > 0 || r.last_eval_error)
              ? (r.enabled
                  ? html`<span class="badge warning plain" title=${r.last_eval_error || ""}>${t("rules.badgeError")}</span>`
                  : html`<span class="badge plain" title=${t("rules.disabledLastErrorTitle", { error: r.last_eval_error || "" })}>${t("rules.badgeOffLastError")}</span>`)
              : r.enabled ? html`<span class="badge ok plain">${t("rules.badgeOn")}</span>` : html`<span class="badge plain">${t("rules.badgeOff")}</span>`}</td>
            <td class="small">${r.persist_n}× / ${r.eval_interval_sec}s</td>
            <td title=${fmtDateTime(r.last_fired_at)}>${r.last_fired_at ? fmtRelative(r.last_fired_at) : "—"}</td>
            <td class="num">${r.fire_count_lifetime}</td>
          </tr>`)}</tbody></table>`}
      ${data ? html`<div style="padding:10px 14px"><${Pager} offset=${data.offset} limit=${data.limit} total=${data.total} onPage=${setOffset} /></div>` : null}
    </div>

    ${editing ? html`<${RuleEditor} key=${editing.__new ? "new:" + (editing.name || "") : "id:" + editing.id}
        rule=${editing} templates=${templates} variables=${variables} rules=${allRules}
        onClose=${closeEditor} onSaved=${() => { closeEditor(); reload(); }}
        onDuplicate=${(r) => setEditing(r)} />` : null}
  </div>`;
}

const EMPTY_R = {
  template_type: "", condition_expr: "", persist_n: 1, eval_interval_sec: 10,
  vars_extract: [], inhibited_by: [], trigger_summary: "", trigger_logic_md: "",
  enabled: true, sort_order: 100,
};

function RuleEditor({ rule, templates, variables, rules, onClose, onSaved, onDuplicate }) {
  const isNew = !!rule.__new;
  const [name, setName] = useState(rule.name || "");
  // A11: stripMeta on a bare {__new:true} yields undefined for every field,
  // which would overwrite the EMPTY_R defaults (Number(undefined) → NaN →
  // 422 on submit). Merge only the DEFINED values so defaults survive.
  const [r, setR] = useState(isNew
    ? { ...EMPTY_R, ...Object.fromEntries(Object.entries(stripMeta(rule)).filter(([, v]) => v !== undefined)) }
    : { ...rule });
  const [validation, setValidation] = useState(null);
  const [evalRes, setEvalRes] = useState(null);
  const [fireRes, setFireRes] = useState(null);
  const [ctxText, setCtxText] = useState("{}");
  const [busy, setBusy] = useState(false);
  const fieldErrs = useFieldErrors();
  const [confirmDel, setConfirmDel] = useState(false);
  const nameOk = /^[a-z][a-z0-9_-]*$/.test(name);

  function set(k, v) { setR((c) => ({ ...c, [k]: v })); }

  async function validate() {
    try { setValidation(await api.post("/v1/rules/validate", { condition_expr: r.condition_expr, vars_extract: r.vars_extract })); }
    catch (e) { toast.error(e); }
  }

  async function save() {
    fieldErrs.clear();
    if (isNew && !nameOk) return toast.error(t("rules.nameToastError"));
    setBusy(true);
    try {
      const payload = {
        template_type: r.template_type, condition_expr: r.condition_expr,
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
  return html`<${Drawer} open=${true} width=${760} title=${isNew ? t("rules.newRule") : rule.name} onClose=${closeDraft} dirty=${dirty}>
      ${draft.recovered ? html`<${DraftBanner} onRestore=${restoreDraft} onDiscard=${draft.dismiss} />` : null}
      <${FieldErrorSummary} errors=${fieldErrs.errors}
        idFor=${(f) => ({ name: "r-name", template_type: "r-tmpl", condition_expr: "r-cond", persist_n: "r-persistn", eval_interval_sec: "r-evalint" }[f.split(".").pop()] || "r-cond")} />
    <div class="editor">
      ${isNew ? html`<div class="field"><label for="r-name">${t("rules.nameLabel")} <span class="req">*</span></label>
        <input id="r-name" value=${name} onInput=${(e) => setName(e.target.value)}
          aria-invalid=${(name && !nameOk) || !!fieldErrs.msgFor("name") || undefined}
          aria-describedby=${fieldErrs.msgFor("name") ? fieldErrorId("name") : undefined} placeholder=${t("rules.namePlaceholder")} />
        ${name && !nameOk ? html`<div class="error small">${t("rules.nameRule")}</div>` : null}
        ${fieldErrs.msgFor("name") ? html`<div id=${fieldErrorId("name")} class="error small" role="alert">${fieldErrs.msgFor("name")}</div>` : null}</div>`
        : html`<p class="muted small mono">${t("rules.idPrefix", { id: rule.id })}${rule.last_eval_error ? html` · <span class="warn-text">${rule.last_eval_error}</span>` : ""}</p>`}

      <div class=${"field" + (fieldErrs.msgFor("template_type") ? " has-error" : "")}><label for="r-tmpl">${t("rules.templateTypeLabel")} <span class="req">*</span></label>
        <input id="r-tmpl" list="rule-tmpls" value=${r.template_type} onInput=${(e) => set("template_type", e.target.value)}
          aria-invalid=${fieldErrs.msgFor("template_type") ? "true" : undefined}
          aria-describedby=${fieldErrs.msgFor("template_type") ? fieldErrorId("template_type") : undefined} placeholder=${t("rules.templatePlaceholder")} />
        <datalist id="rule-tmpls">${templates.map((tt) => html`<option key=${tt} value=${tt}></option>`)}</datalist>
        ${fieldErrs.msgFor("template_type") ? html`<div id=${fieldErrorId("template_type")} class="error small" role="alert">${fieldErrs.msgFor("template_type")}</div>` : null}</div>

      <div class=${"field" + (fieldErrs.msgFor("condition_expr") ? " has-error" : "")}><label for="r-cond">${t("rules.conditionLabel")} <span class="req">*</span></label>
        <textarea id="r-cond" rows="3" class="mono" value=${r.condition_expr} onInput=${(e) => { set("condition_expr", e.target.value); setValidation(null); }}
          aria-invalid=${fieldErrs.msgFor("condition_expr") ? "true" : undefined}
          aria-describedby=${fieldErrs.msgFor("condition_expr") ? fieldErrorId("condition_expr") : undefined}
          placeholder=${t("rules.conditionPlaceholder")} spellcheck="false"></textarea>
        ${fieldErrs.msgFor("condition_expr") ? html`<div id=${fieldErrorId("condition_expr")} class="error small" role="alert">${fieldErrs.msgFor("condition_expr")}</div>` : null}
        <div class="form-actions"><button type="button" class="btn sm" onClick=${validate}>${t("rules.validate")}</button>
          ${validation ? (validation.ok ? html`<span class="badge ok plain">${t("rules.validateOk", { result: JSON.stringify(validation.result) })}</span>`
            : html`<span class="badge critical plain">${t("rules.badgeError")}</span> <span class="error small">${validation.error}</span>`) : null}</div>
        ${validation ? html`<div class="validation">
          ${validation.referenced_vars?.length ? html`<div class="small"><b>${t("rules.referenced")}</b> ${validation.referenced_vars.map((v) => html`<span key=${v.name} class=${"chip " + (v.present ? (v.is_stale ? "warn" : "") : "crit")}
            title=${v.present ? t("rules.varPresentTitle", { value: JSON.stringify(v.live_value), age: Math.round(v.age_sec), stale: v.is_stale ? t("rules.varStaleSuffix") : "" }) : t("rules.varUnknown")}>${v.name}</span>`)}</div>` : null}
          ${validation.unknown_vars?.length ? html`<div class="small warn-text">${t("rules.unknownVars", { vars: validation.unknown_vars.join(", ") })}</div>` : null}
        </div>` : null}
      </div>

      <details class="cheat"><summary>${t("rules.cheatSheet")}</summary>
        <table class="tbl small">${cheats().map(([fn, d]) => html`<tr key=${fn}><td class="mono">${fn}</td><td class="muted">${d}</td></tr>`)}</table>
      </details>

      <div class="row2">
        <div class="field"><label for="r-persistn">${t("rules.persistN")}</label><input id="r-persistn" type="number" value=${r.persist_n} onInput=${(e) => set("persist_n", e.target.value)} /></div>
        <div class="field"><label for="r-evalint">${t("rules.evalInterval")}</label><input id="r-evalint" type="number" value=${r.eval_interval_sec} onInput=${(e) => set("eval_interval_sec", e.target.value)} /></div>
      </div>

      <div class="field"><label for="r-vars">${t("rules.varsCapture")}</label>
        <${TagInput} inputId="r-vars" ariaLabel=${t("rules.varsCapture")} value=${r.vars_extract} onChange=${(v) => set("vars_extract", v)} options=${variables} placeholder=${t("rules.varNamePlaceholder")} /></div>
      <div class="field"><label for="r-inhib">${t("rules.inhibitedBy")}</label>
        <${TagInput} inputId="r-inhib" ariaLabel=${t("rules.inhibitedByAria")} value=${r.inhibited_by} onChange=${(v) => set("inhibited_by", v)} options=${rules} placeholder=${t("rules.ruleNamePlaceholder")} /></div>

      <div class="field"><label for="r-summary">${t("rules.triggerSummary")}</label><input id="r-summary" value=${r.trigger_summary || ""} onInput=${(e) => set("trigger_summary", e.target.value)} /></div>
      <div class="row2">
        <div class="field"><label for="r-sort">${t("rules.sortOrder")}</label><input id="r-sort" type="number" value=${r.sort_order} onInput=${(e) => set("sort_order", e.target.value)} /></div>
        <div class="field"><label class="chk"><input type="checkbox" checked=${r.enabled} onChange=${(e) => set("enabled", e.target.checked)} /> ${t("rules.enabled")}</label></div>
      </div>

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
    inhibited_by, trigger_summary, trigger_logic_md, enabled, sort_order } = r;
  return { template_type, condition_expr, persist_n, eval_interval_sec,
    vars_extract: vars_extract || [], inhibited_by: inhibited_by || [],
    trigger_summary, trigger_logic_md, enabled, sort_order };
}
