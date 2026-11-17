// Templates (phase F5): list grouped by category + an editor with live
// preview, channel routing, test fire and a typed-confirm delete.
import { html, useState, useMemo, useEffect } from "../lib/h.js";
import { clickable } from "../lib/a11y.js";
import { useLoader } from "../lib/loader.js";
import { api, getAll } from "../lib/api.js";
import { lookup } from "../lib/lookup.js";
import { toast } from "../lib/toast.js";
import { Drawer, useDirty, Spinner, Empty, ErrorState, StaleBanner, DangerConfirm, Json, ListMeta, KindHelp, DraftBanner, starterActions } from "../lib/ui.js";
import { useDraft } from "../lib/draft.js";
import { renderTemplate, placeholderNames, sampleContext } from "../lib/render.js";
import { IconPicker } from "../lib/icon_picker.js";
import { isValidIcon } from "../lib/icons.js";
import { canonicalCategories } from "../lib/categories.js";
import { TransferMenu } from "../lib/transfer.js";
import { useFieldErrors, FieldErrorSummary, FieldMsg } from "../lib/form.js";
import { t, tnode } from "../lib/i18n.js";
import { sevLabel, reasonLabel } from "../lib/labels.js";

const SEVERITIES = ["info", "warning", "critical"];

export function TemplatesView({ query } = {}) {
  // ?search= opens the page filtered (e.g. from the Ctrl+K search).
  const [filters, setFilters] = useState({ search: query?.search || "", severity: "", enabled: "" });
  useEffect(() => { if (query?.search !== undefined) setFilters((f) => ({ ...f, search: query.search })); }, [query?.search]);
  const [editing, setEditing] = useState(null);

  // Debounced + cancelable load with a stale-response guard (audit A28).
  const [page, , reload, error] = useLoader(async (signal) => {
    const q = { limit: 500 };
    if (filters.severity) q.severity = filters.severity;
    if (filters.enabled) q.enabled = filters.enabled;
    if (filters.search) q.search = filters.search;
    return api.get("/v1/templates", q, { signal });
  }, [filters]);
  const all = page?.items ?? null;
  const total = page?.total ?? null;

  // Case-insensitive: "grid" and "Grid" are one category shown with the most
  // used spelling (the server canonicalises new writes the same way).
  const categories = useMemo(() => canonicalCategories(all || []), [all]);
  const grouped = useMemo(() => {
    const label = new Map(categories.map((c) => [c.toLowerCase(), c]));
    const g = {};
    for (const tpl of all || []) {
      const k = tpl.category ? label.get(tpl.category.toLowerCase()) : t("templates.uncategorized");
      (g[k] ||= []).push(tpl);
    }
    return Object.entries(g).sort((a, b) => a[0].localeCompare(b[0]));
  }, [all, categories]);

  function setF(k, v) { setFilters((f) => ({ ...f, [k]: v })); }

  return html`<div>
    <div class="page-head">
      <div><h1>${t("templates.title")}</h1><p class="muted">${t("templates.subtitle")}</p></div>
      <div class="actions">
        <${TransferMenu} section="templates" shownNames=${(all || []).map((x) => x.type)}
          filtered=${Object.values(filters).some(Boolean)} onImported=${reload} />
        <button class="btn primary" onClick=${() => setEditing({ __new: true })}>${t("templates.newTemplate")}</button></div>
    </div>

    <div class="card filters">
      <input class="grow" aria-label=${t("templates.searchAria")} placeholder=${t("templates.searchPlaceholder")} value=${filters.search} onInput=${(e) => setF("search", e.target.value)} />
      <select aria-label=${t("templates.filterSeverityAria")} value=${filters.severity} onChange=${(e) => setF("severity", e.target.value)}>
        <option value="">${t("templates.anySeverity")}</option>${SEVERITIES.map((s) => html`<option key=${s} value=${s}>${sevLabel(s)}</option>`)}
      </select>
      <select aria-label=${t("templates.filterStateAria")} value=${filters.enabled} onChange=${(e) => setF("enabled", e.target.value)}>
        <option value="">${t("templates.anyState")}</option><option value="true">${t("templates.enabled")}</option><option value="false">${t("templates.disabled")}</option>
      </select>
    </div>

    <${ListMeta} total=${total} limit=${500} />
    ${error && all ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    ${error && all === null ? html`<${ErrorState} error=${error} onRetry=${reload} />` : all === null ? html`<${Spinner} />` : all.length === 0
        ? html`<div class="card"><${Empty} title=${t("templates.blank.title")} body=${t("templates.blank.body")}
            actions=${[{ label: t("templates.newTemplate"), primary: true, onClick: () => setEditing({ __new: true }) }, ...starterActions()]} /></div>`
      : grouped.length === 0 ? html`<div class="card" style="margin-top:14px"><${Empty} filtered onClear=${() => setFilters({ search: "", severity: "", enabled: "" })} /></div>`
      : html`<div style="margin-top:14px">${grouped.map(([cat, items]) => html`<div key=${cat} class="tmpl-group">
          <div class="nav-title">${cat} <span class="muted">· ${items.length}</span></div>
          <div class="card" style="padding:0">
            <table class="tbl"><tbody>${items.map((tpl) => html`<tr key=${tpl.type} ...${clickable(() => setEditing(tpl), t("templates.editAria", { type: tpl.type }))} style="cursor:pointer">
              <td style="width:26px">${isValidIcon(tpl.icon) ? (tpl.icon || "")
                : html`<span class="chip crit" title=${t("templates.invalidIconTitle", { icon: tpl.icon })}>${t("templates.invalidIconShort")}</span>`}</td>
              <td><b>${tpl.type}</b><div class="muted small">${tpl.title_template}</div></td>
              <td><span class="badge ${tpl.severity} plain sev">${sevLabel(tpl.severity)}</span></td>
              <td>${tpl.enabled ? "" : html`<span class="badge plain">${t("templates.disabledBadge")}</span>`}</td>
            </tr>`)}</tbody></table>
          </div>
        </div>`)}</div>`}

    ${editing ? html`<${TemplateEditor} template=${editing} categories=${categories}
        onClose=${() => setEditing(null)} onSaved=${() => { setEditing(null); reload(); }} />` : null}
  </div>`;
}

const EMPTY_T = {
  severity: "warning", icon: "", category: "", title_template: "", message_template: "",
  runbook_url: "", description: "", locale: "en", min_repeat_min: 30, gate_variable: "", gate_min: null,
  quiet_hours: null, enabled: true,
};

function TemplateEditor({ template, categories, onClose, onSaved }) {
  const isNew = !!template.__new;
  const [type, setType] = useState(isNew ? "" : template.type);
  const [tpl, setTpl] = useState(isNew ? { ...EMPTY_T } : { ...template });
  // Preview context: filled from the placeholders the title / message use
  // (live variable values, else samples) until the user edits it.
  const [ctxText, setCtxText] = useState("{}");
  const [ctxTouched, setCtxTouched] = useState(false);
  const [liveValues, setLiveValues] = useState({});
  const [routes, setRoutes] = useState(null);
  const [routesDirty, setRoutesDirty] = useState(false); // route edits mark the editor dirty (UX-007/R2)     // {channelId: {routed, severity_min, enabled, channel_overrides}}
  const [routesError, setRoutesError] = useState(false);  // route load failed → never PUT (F19)
  const [channels, setChannels] = useState([]);
  const [intrusiveKinds, setIntrusiveKinds] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const fieldErrs = useFieldErrors();
  // If POST succeeds but the routing PUT then fails, the type already exists;
  // remember it so a retry PATCHes instead of re-POSTing (which would 409) and
  // the partial create can be finished (audit UX-020).
  const [createdType, setCreatedType] = useState(null);
  const [fireResult, setFireResult] = useState(null);
  const [ruleRefs, setRuleRefs] = useState(0);
  const [confirmDel, setConfirmDel] = useState(false);
  const [variableNames, setVariableNames] = useState([]);

  function set(k, v) { setTpl((cur) => ({ ...cur, [k]: v })); }

  // Load channels + existing routes (edit only) + rule reference count.
  useEffect(() => {
    lookup(getAll("/v1/channels").then((p) => setChannels(p.items)));
    lookup(getAll("/v1/variables").then((p) => setVariableNames(p.items.map((v) => v.name).sort())));
    lookup(api.get("/v1/meta/kinds").then((m) => setIntrusiveKinds(new Set(
      Object.entries(m.channels || {}).filter(([, d]) => d.intrusive).map(([k]) => k)))));
    if (!isNew) {
      api.get(`/v1/templates/${encodeURIComponent(template.type)}/channels`).then((rs) => {
        const m = {};
        // Preserve the full route object, including channel_overrides, so a
        // Save that doesn't touch routing re-sends it instead of nulling it
        // out on the complete-replacement PUT (F19). Overrides are masked on
        // read; the server preserves real secrets on MASK echo (F02).
        for (const r of rs) m[r.channel_id] = {
          routed: true, severity_min: r.severity_min, enabled: r.enabled,
          channel_overrides: r.channel_overrides ?? null,
        };
        setRoutes(m);
      }).catch(() => { setRoutes(null); setRoutesError(true); });
      lookup(api.get("/v1/rules", { template_type: template.type, limit: 1 }).then((p) => setRuleRefs(p.total)));
    } else { setRoutes({}); }
  }, []);

  // Live preview (client-side render of the unsaved title/message).
  const usedNames = placeholderNames(tpl.title_template, tpl.message_template).join("\n");
  const suggested = useMemo(() => JSON.stringify(sampleContext(usedNames ? usedNames.split("\n") : [], liveValues), null, 2), [usedNames, liveValues]);
  useEffect(() => { if (!ctxTouched) setCtxText(suggested); }, [suggested, ctxTouched]);
  useEffect(() => {
    // Live values only seed the preview; without them it uses sample values.
    lookup(api.get("/v1/state").then((st) => setLiveValues(Object.fromEntries((st.variables || [])
      .filter((v) => v.value !== null && v.value !== undefined).map((v) => [v.name, v.value])))));
  }, []);
  const ctx = useMemo(() => { try { return JSON.parse(ctxText || "{}"); } catch { return null; } }, [ctxText]);
  const titlePrev = ctx ? renderTemplate(tpl.title_template, ctx) : null;
  const msgPrev = ctx ? renderTemplate(tpl.message_template, ctx) : null;
  const missing = [...new Set([...(titlePrev?.missing || []), ...(msgPrev?.missing || [])])];

  function routeFor(id) { return (routes && routes[id]) || { routed: false, severity_min: "info", enabled: true }; }
  function setRoute(id, patch) { setRoutesDirty(true); setRoutes((r) => ({ ...r, [id]: { ...routeFor(id), ...patch } })); }

  async function save() {
    fieldErrs.clear();
    const gateVar = (tpl.gate_variable || "").trim();
    const gateMin = tpl.gate_min === "" || tpl.gate_min == null ? null : tpl.gate_min;
    if (!fieldErrs.check([
      ["type", !isNew || createdType || /^[a-z][a-z0-9_]*$/.test(type), type ? t("templates.toastTypeError") : null],
      ["title_template", (tpl.title_template || "").trim()],
      // The gate needs both halves; one without the other silently does nothing.
      ["gate_variable", !(gateMin !== null && !gateVar), t("templates.gateNeedsVariable")],
      ["gate_min", !(gateVar && gateMin === null), t("templates.gateNeedsMin")],
    ])) return;
    setBusy(true);
    try {
      const payload = {
        severity: tpl.severity, icon: tpl.icon || null, category: tpl.category || null,
        title_template: tpl.title_template, message_template: tpl.message_template || null,
        runbook_url: tpl.runbook_url || null, description: tpl.description || null,
        locale: tpl.locale || "en", min_repeat_min: Number(tpl.min_repeat_min),
        gate_variable: (tpl.gate_variable || "").trim() || null,
        gate_min: tpl.gate_min === "" || tpl.gate_min == null ? null : Number(tpl.gate_min),
        quiet_hours: tpl.quiet_hours, enabled: tpl.enabled,
      };
      const theType = isNew ? type : template.type;
      // A previous attempt may have created the type already; PATCH it rather
      // than POST again (which would 409) so the partial create can finish.
      if (!isNew || createdType) await api.patch(`/v1/templates/${encodeURIComponent(theType)}`, payload);
      else { await api.post("/v1/templates", { type, ...payload }); setCreatedType(theType); }

      // Never send the complete-replacement routing PUT when routes failed
      // to load — an empty/partial body would unlink every real route (F19).
      if (routes && !routesError) {
        const body = Object.entries(routes).filter(([, r]) => r.routed)
          .map(([cid, r]) => {
            const row = { channel_id: Number(cid), severity_min: r.severity_min, enabled: r.enabled };
            if (r.channel_overrides != null) row.channel_overrides = r.channel_overrides;
            return row;
          });
        await api.put(`/v1/templates/${encodeURIComponent(theType)}/channels`, body);
      }
      toast.ok(isNew ? t("templates.toastCreated") : t("templates.toastSaved"));
      draft.clear();
      onSaved();
    } catch (e) { if (!fieldErrs.show(e)) toast.error(e); } finally { setBusy(false); }
  }

  // The server renders the SAVED template over its SAVED routes, and a test
  // fire skips throttling — so it is offered only for what is saved, and once
  // at a time: a double tap must not send two real notifications (UX-05).
  async function testFire() {
    if (!ctx) return toast.error(t("templates.toastInvalidJson"));
    setFireResult(null); setBusy(true);
    try { setFireResult(await api.post("/v1/fire", { type: isNew ? type : template.type, context: ctx, test: true })); }
    catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  async function doDelete() {
    setBusy(true);
    try { await api.del(`/v1/templates/${encodeURIComponent(template.type)}`); toast.ok(t("templates.toastDeleted")); draft.clear(); onSaved(); }
    catch (e) { toast.error(e); setConfirmDel(false); } finally { setBusy(false); }
  }

  const dirty = useDirty({ type, tpl }) || routesDirty;
  // Nothing saved yet, or edits on screen the server does not have.
  const unsaved = (isNew && !createdType) || dirty;
  // Draft recovery (UX-007) covers the template body; channel routes reload
  // from the server on reopen and aren't part of the stashed draft.
  const draft = useDraft("templates", isNew ? null : template.type, { type, tpl }, dirty);
  const restoreDraft = () => { const d = draft.recovered; setType(d.type); setTpl(d.tpl); draft.restore(); };
  const closeDraft = () => { draft.clear(); onClose(); };
  return html`<${Drawer} open=${true} width=${720} title=${isNew ? t("templates.newTemplate") : template.type} onClose=${closeDraft} dirty=${dirty}>
      ${draft.recovered ? html`<${DraftBanner} onRestore=${restoreDraft} onDiscard=${draft.dismiss} />` : null}
      <${FieldErrorSummary} errors=${fieldErrs.errors}
        idFor=${(f) => ({ type: "t-type", title_template: "t-title", gate_variable: "t-gatevar", gate_min: "t-gatemin", message_template: "t-msg", severity: "t-severity", category: "t-category", locale: "t-locale" }[f.split(".").pop()] || "t-title")} />
    <div class="editor">
      ${isNew ? html`<div class="field"><label for="t-type">${t("templates.typeLabel")} <span class="req">*</span></label>
        <input id="t-type" value=${type} onInput=${(e) => setType(e.target.value)} placeholder=${t("templates.typePlaceholder")} ...${fieldErrs.attrs("type")} />
        <${FieldMsg} fe=${fieldErrs} name="type" />
        <div class="hint">${t("templates.typeHint")}</div></div>`
        : html`<p class="muted small mono">${t("templates.typePrefix", { type: template.type })}${ruleRefs ? t("templates.ruleRefs", { count: ruleRefs }) : ""}</p>`}

      <div class="row2">
        <div class="field"><label for="t-severity">${t("templates.severityLabel")}</label>
          <select id="t-severity" value=${tpl.severity} onChange=${(e) => set("severity", e.target.value)}>${SEVERITIES.map((s) => html`<option key=${s} value=${s}>${sevLabel(s)}</option>`)}</select></div>
        <div class="field"><label for="t-icon">${t("templates.iconLabel")}</label>
          <${IconPicker} id="t-icon" value=${tpl.icon || ""} onChange=${(v) => set("icon", v)} /></div>
      </div>
      <div class="row2">
        <div class="field"><label for="t-category">${t("templates.categoryLabel")}</label>
          <input id="t-category" list="tmpl-cats" value=${tpl.category || ""} onInput=${(e) => set("category", e.target.value)} placeholder=${t("templates.categoryPlaceholder")} />
          <datalist id="tmpl-cats">${categories.map((c) => html`<option key=${c} value=${c}></option>`)}</datalist></div>
        <div class="field"><label for="t-locale">${t("templates.localeLabel")}</label><input id="t-locale" value=${tpl.locale || ""} onInput=${(e) => set("locale", e.target.value)} /></div>
      </div>

      <div class="field"><label for="t-title">${t("templates.titleTemplateLabel")} <span class="req">*</span></label>
        <input id="t-title" value=${tpl.title_template} onInput=${(e) => set("title_template", e.target.value)} placeholder=${t("templates.titlePlaceholder")} ...${fieldErrs.attrs("title_template")} />
        <${FieldMsg} fe=${fieldErrs} name="title_template" /></div>
      <div class="field"><label for="t-msg">${t("templates.messageTemplateLabel")}</label>
        <textarea id="t-msg" rows="3" value=${tpl.message_template || ""} onInput=${(e) => set("message_template", e.target.value)}></textarea></div>

      <!-- Live preview -->
      <div class="preview">
        <div class="preview-head"><b>${t("templates.livePreview")}</b> <label for="t-ctx" class="muted small">${t("templates.contextJson")}</label></div>
        <textarea id="t-ctx" rows="3" class=${"mono" + (ctx ? "" : " invalid")} value=${ctxText}
          onInput=${(e) => { setCtxText(e.target.value); setCtxTouched(true); }} spellcheck="false" aria-describedby="t-ctx-hint"></textarea>
        <div id="t-ctx-hint" class="hint">${t("templates.ctxHint")}
          ${ctxTouched ? html` <button type="button" class="link-btn" onClick=${() => { setCtxTouched(false); setCtxText(suggested); }}>${t("templates.ctxRefill")}</button>` : null}</div>
        ${ctx ? html`<div class="preview-out">
          <div class="preview-title">${tpl.icon || ""} ${titlePrev.text || html`<span class="muted">${t("templates.emptyTitle")}</span>`}</div>
          ${tpl.message_template ? html`<div class="preview-msg">${msgPrev.text}</div>` : null}
          ${missing.length ? html`<div class="small warn-text">${t("templates.missing", { fields: missing.join(", ") })}</div>` : null}
        </div>` : html`<div class="error small">${t("templates.invalidJson")}</div>`}
      </div>

      <div class="field"><label for="t-minrepeat">${t("templates.minRepeat")}</label><input id="t-minrepeat" type="number" value=${tpl.min_repeat_min} onInput=${(e) => set("min_repeat_min", e.target.value)} /></div>
      <fieldset class="gate">
        <legend>${t("templates.gateLegend")}</legend>
        <p class="hint">${t("templates.gateHint")}</p>
        <div class="row2">
          <div class="field"><label for="t-gatevar">${t("templates.gateVariable")}</label>
            <input id="t-gatevar" class="mono" list="tmpl-gate-vars" value=${tpl.gate_variable || ""} onInput=${(e) => set("gate_variable", e.target.value)}
              placeholder=${t("templates.optionalPlaceholder")} ...${fieldErrs.attrs("gate_variable")} />
            <datalist id="tmpl-gate-vars">${variableNames.map((n) => html`<option key=${n} value=${n}></option>`)}</datalist>
            <${FieldMsg} fe=${fieldErrs} name="gate_variable" /></div>
          <div class="field"><label for="t-gatemin">${t("templates.gateMin")}</label>
            <input id="t-gatemin" type="number" step="any" value=${tpl.gate_min ?? ""} onInput=${(e) => set("gate_min", e.target.value)}
              placeholder=${t("templates.optionalPlaceholder")} ...${fieldErrs.attrs("gate_min")} />
            <${FieldMsg} fe=${fieldErrs} name="gate_min" /></div>
        </div>
        ${(tpl.gate_variable || "").trim() && tpl.gate_min !== "" && tpl.gate_min != null
          ? html`<p class="small muted">${t("templates.gateSummary", { variable: tpl.gate_variable.trim(), min: tpl.gate_min })}</p>` : null}
      </fieldset>
      <div class="field"><label for="t-runbook">${t("templates.runbookLabel")}</label><input id="t-runbook" value=${tpl.runbook_url || ""} onInput=${(e) => set("runbook_url", e.target.value)} placeholder=${t("templates.runbookPlaceholder")} /></div>
      <div class="field"><label for="t-desc">${t("templates.descriptionLabel")}</label><textarea id="t-desc" rows="2" value=${tpl.description || ""} onInput=${(e) => set("description", e.target.value)}></textarea></div>
      <div class="field"><label class="chk"><input type="checkbox" checked=${tpl.enabled} onChange=${(e) => set("enabled", e.target.checked)} /> ${t("templates.enabled")}</label></div>

      <!-- Routing -->
      <h3 class="why-h">${t("templates.routingHeading")}</h3>
      ${routesError ? html`<p class="muted small error">${t("templates.routesFailedLoad")}</p>`
        : routes === null ? html`<${Spinner} label=${t("templates.loadingRoutes")} />` : channels.length === 0
        ? html`<p class="muted small">${t("templates.noChannels")}</p>`
        : html`<table class="tbl routing"><thead><tr><th><span class="sr-only">${t("templates.colRouted")}</span></th><th>${t("templates.colChannel")}</th><th>${t("templates.colMinSeverity")}</th><th>${t("templates.colOn")}</th></tr></thead>
          <tbody>${channels.map((c) => { const r = routeFor(c.id); return html`<tr key=${c.id}>
            <td><input type="checkbox" aria-label=${t("templates.routeToAria", { name: c.name })} checked=${r.routed} onChange=${(e) => setRoute(c.id, { routed: e.target.checked })} /></td>
            <td><b>${c.name}</b> <span class="muted small mono">${c.kind}</span>
              ${intrusiveKinds.has(c.kind) ? html` <span class="chip warn" title=${t("templates.intrusiveTitle")}>${t("templates.intrusive")}</span>` : null}</td>
            <td><select aria-label=${t("templates.minSeverityAria", { name: c.name })} value=${r.severity_min} disabled=${!r.routed} onChange=${(e) => setRoute(c.id, { severity_min: e.target.value })}>
              ${SEVERITIES.map((s) => html`<option key=${s} value=${s}>${sevLabel(s)}</option>`)}</select></td>
            <td><input type="checkbox" aria-label=${t("templates.enableRouteAria", { name: c.name })} checked=${r.enabled} disabled=${!r.routed} onChange=${(e) => setRoute(c.id, { enabled: e.target.checked })} /></td>
          </tr>`; })}</tbody></table>`}
      ${(() => {
        const noisy = intrusiveWarnings(tpl.severity, channels, routes, intrusiveKinds);
        return noisy.length ? html`<p class="alert warn small" role="status">${t("templates.intrusiveInfoWarning", { channels: noisy.join(", ") })}</p>` : null;
      })()}

      ${createdType ? html`<p class="validation warn-text small" role="status">${t("templates.partialCreateNote")}</p>` : null}
      <div class="editor-actions">
        <button class="btn primary" onClick=${save} disabled=${busy || !isValidIcon(tpl.icon)}>${isNew && !createdType ? t("templates.create") : t("templates.save")}</button>
        <button class="btn" onClick=${testFire} disabled=${busy || !ctx || unsaved}
          aria-describedby=${unsaved ? "tpl-test-hint" : undefined}>${t("templates.testFire")}</button>
        ${!isNew ? html`<span class="spacer"></span><button class="btn danger" onClick=${() => setConfirmDel(true)} disabled=${busy}>${t("templates.delete")}</button>` : null}
      </div>

      ${unsaved ? html`<p id="tpl-test-hint" class="hint small">${t("templates.testFireSaved")}</p>` : null}
      ${fireResult ? html`<div class="result"><b>${t("templates.firedResult")}</b> ${fireResult.dispatched ? html`<span class="badge ok plain">${t("templates.dispatched")}</span>` : html`<span class="badge warning plain">${fireResult.suppressed_reason ? reasonLabel(fireResult.suppressed_reason) : t("templates.notDispatched")}</span>`}
        <a href=${`#/log?search=${encodeURIComponent(isNew ? type : template.type)}`} onClick=${onClose}>${t("templates.viewInLog")}</a>
        <${Json} value=${fireResult} /></div>` : null}

      <${KindHelp} help=${tnode("templates.help")} />
    </div>

    <${DangerConfirm} open=${confirmDel} token=${template.type} title=${t("templates.deleteTitle", { type: template.type })}
      warning=${ruleRefs ? t("templates.deleteWarning", { count: ruleRefs }) : null}
      busy=${busy} onConfirm=${doDelete} onClose=${() => setConfirmDel(false)} />
  </${Drawer}>`;
}

export { canonicalCategories };

// Channels where an `info` alert of this template would actually land although
// the channel kind is intrusive (can wake someone / costs money — roadmap §5).
export function intrusiveWarnings(severity, channels, routes, intrusiveKinds) {
  if (severity !== "info" || !routes) return [];
  return channels.filter((c) => {
    const r = routes[c.id];
    return intrusiveKinds.has(c.kind) && r && r.routed && r.enabled && (r.severity_min || "info") === "info";
  }).map((c) => c.name);
}
