// Schedules (phase F6): list + editor with a live cron preview and a
// test fire.
import { html, useState, useEffect, useCallback } from "../lib/h.js";
import { useGuard } from "../lib/action.js";
import { useLoader } from "../lib/loader.js";
import { clickable } from "../lib/a11y.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { Drawer, useDirty, Spinner, Empty, ErrorState, StaleBanner, Json, DangerConfirm, ListMeta, DraftBanner } from "../lib/ui.js";
import { useDraft } from "../lib/draft.js";
import { useFieldErrors, FieldErrorSummary, FieldMsg, fieldErrorId } from "../lib/form.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import { t } from "../lib/i18n.js";

export function SchedulesView() {
  const [templates, setTemplates] = useState([]);
  const [templatesErr, setTemplatesErr] = useState(false);
  const [editing, setEditing] = useState(null);

  // useLoader gives a persistent error + retry (ErrorState on first load,
  // StaleBanner on a failed refresh), with abort/stale-response guards — the
  // previous catch→toast left a permanent spinner on a failed load (UX-006/R1).
  const [data, , reload, error] = useLoader(() => api.get("/v1/schedules", { limit: 500 }), []);
  const items = data?.items ?? null;
  const total = data?.total ?? null;
  const load = reload;
  // Template names power the type autocomplete only (the field is free-text), so
  // a failure is non-fatal — but it was swallowed silently, leaving an operator
  // wondering where the suggestions went. Flag it so the editor can say so and
  // offer a retry instead of pretending there are no templates (UX-006).
  const loadTemplates = useCallback(() => {
    api.get("/v1/templates", { limit: 500 })
      .then((p) => { setTemplates(p.items.map((x) => x.type).sort()); setTemplatesErr(false); })
      .catch(() => setTemplatesErr(true));
  }, []);
  useEffect(() => { loadTemplates(); }, [loadTemplates]);

  return html`<div>
    <div class="page-head">
      <div><h1>${t("schedules.title")}</h1><p class="muted">${t("schedules.intro")}</p></div>
      <div class="actions"><button class="btn primary" onClick=${() => setEditing({ __new: true })}>${t("schedules.newSchedule")}</button></div>
    </div>

    <${ListMeta} total=${total} limit=${500} />
    ${error && items ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    <div class="card" style="padding:0">
      ${error && items === null ? html`<${ErrorState} error=${error} onRetry=${reload} />` : items === null ? html`<${Spinner} />` : items.length === 0 ? html`<${Empty} title=${t("schedules.blank.title")} body=${t("schedules.blank.body")}
        actions=${[{ label: t("schedules.newSchedule"), primary: true, onClick: () => setEditing({ __new: true }) }, { label: t("schedules.blank.templates"), href: "#/templates" }]} />`
        : html`<table class="tbl"><thead><tr><th>${t("schedules.colName")}</th><th>${t("schedules.colCron")}</th><th>${t("schedules.colTemplate")}</th><th>${t("schedules.colNext")}</th><th>${t("schedules.colLast")}</th><th>${t("schedules.colState")}</th></tr></thead>
          <tbody>${items.map((s) => html`<tr key=${s.id} ...${clickable(() => setEditing(s), t("schedules.editAria", { name: s.name }))} style="cursor:pointer">
            <td><b>${s.name}</b></td><td class="mono small">${s.cron_expr}</td><td class="mono small">${s.template_type}</td>
            <td title=${fmtDateTime(s.next_fire_at)}>${s.next_fire_at ? fmtRelative(s.next_fire_at) : "—"}</td>
            <td title=${fmtDateTime(s.last_fired_at)}>${s.last_fired_at ? fmtRelative(s.last_fired_at) : "—"}</td>
            <td>${s.enabled ? html`<span class="badge ok plain">${t("schedules.badgeOn")}</span>` : html`<span class="badge plain">${t("schedules.badgeOff")}</span>`}</td>
          </tr>`)}</tbody></table>`}
    </div>

    ${editing ? html`<${ScheduleEditor} schedule=${editing} templates=${templates}
        templatesErr=${templatesErr} onReloadTemplates=${loadTemplates}
        onClose=${() => setEditing(null)} onSaved=${() => { setEditing(null); load(); }} />` : null}
  </div>`;
}

function ScheduleEditor({ schedule, templates, templatesErr, onReloadTemplates, onClose, onSaved }) {
  const isNew = !!schedule.__new;
  const [name, setName] = useState(isNew ? "" : schedule.name);
  const [cron, setCron] = useState(isNew ? "0 21 * * *" : schedule.cron_expr);
  const [templateType, setTemplateType] = useState(isNew ? "" : schedule.template_type);
  const [ctxText, setCtxText] = useState(isNew ? "{}" : JSON.stringify(schedule.context || {}, null, 2));
  const [enabled, setEnabled] = useState(isNew ? true : schedule.enabled);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [acting, guard] = useGuard();
  const [confirmDel, setConfirmDel] = useState(false);
  const fe = useFieldErrors();

  // Live cron preview (debounced).
  useEffect(() => {
    if (!cron) { setPreview(null); return undefined; }
    // Abort + guard so a slow preview for a previous cron expression can't
    // replace the preview for the one in the field now (audit UX-010).
    let active = true;
    const ac = new AbortController();
    const h = setTimeout(() => {
      api.get("/v1/schedules/preview", { cron, n: 5 }, { signal: ac.signal })
        .then((r) => { if (active) setPreview(r); })
        .catch((e) => { if (active && e && e.name !== "AbortError") setPreview({ error: true }); });
    }, 300);
    return () => { active = false; ac.abort(); clearTimeout(h); };
  }, [cron]);

  function parseCtx() { try { return JSON.parse(ctxText || "{}"); } catch { return undefined; } }

  async function save() {
    fe.clear();
    const ctx = parseCtx();
    if (!fe.check([
      ["name", !isNew || /^[a-z][a-z0-9_-]*$/.test(name), name ? t("schedules.nameRule") : null],
      ["cron_expr", cron.trim()],
      ["template_type", templateType.trim()],
      ["context", ctx !== undefined, t("schedules.ctxInvalid")],
    ])) return;
    setBusy(true);
    try {
      const payload = { cron_expr: cron, template_type: templateType, context: ctx, enabled };
      if (isNew) await api.post("/v1/schedules", { name, ...payload });
      else await api.patch(`/v1/schedules/${schedule.id}`, payload);
      toast.ok(isNew ? t("schedules.created") : t("schedules.saved"));
      draft.clear();
      onSaved();
    } catch (e) { if (!fe.show(e)) toast.error(e); } finally { setBusy(false); }
  }
  function test() {
    return guard(async () => {
      try { const r = await api.post(`/v1/schedules/${schedule.id}/test`); toast.ok(r.dispatched ? t("schedules.firedDispatched") : t("schedules.firedSuppressed", { reason: r.suppressed_reason || t("schedules.notDispatched") })); }
      catch (e) { toast.error(e); }
    });
  }
  async function doDelete() {
    setBusy(true);
    try { await api.del(`/v1/schedules/${schedule.id}`); toast.ok(t("schedules.deleted")); draft.clear(); onSaved(); }
    catch (e) { toast.error(e); setConfirmDel(false); } finally { setBusy(false); }
  }

  const dirty = useDirty({ name, cron, templateType, ctxText, enabled });
  const draft = useDraft("schedules", isNew ? null : schedule.id, { name, cron, templateType, ctxText, enabled }, dirty);
  const restoreDraft = () => { const d = draft.recovered; setName(d.name); setCron(d.cron); setTemplateType(d.templateType); setCtxText(d.ctxText); setEnabled(d.enabled); draft.restore(); };
  const closeDraft = () => { draft.clear(); onClose(); };
  return html`<${Drawer} open=${true} width=${600} title=${isNew ? t("schedules.newScheduleTitle") : schedule.name} onClose=${closeDraft} dirty=${dirty}>
    ${draft.recovered ? html`<${DraftBanner} onRestore=${restoreDraft} onDiscard=${draft.dismiss} />` : null}
    <${FieldErrorSummary} errors=${fe.errors}
      idFor=${(f) => ({ name: "s-name", cron_expr: "s-cron", template_type: "s-tmpl", context: "s-ctx" }[f.split(".").pop()] || "s-cron")} />
    <div class="editor">
      ${isNew ? html`<div class="field"><label for="s-name">${t("schedules.fieldName")} <span class="req">*</span></label>
        <input id="s-name" value=${name} onInput=${(e) => setName(e.target.value)}
          aria-invalid=${fe.msgFor("name") ? "true" : undefined} aria-describedby=${fe.msgFor("name") ? fieldErrorId("name") : undefined} placeholder=${t("schedules.namePlaceholder")} />
        ${fe.msgFor("name") ? html`<div id=${fieldErrorId("name")} class="error small" role="alert">${fe.msgFor("name")}</div>` : null}</div>`
        : html`<p class="muted small mono">id ${schedule.id}</p>`}

      <div class=${"field" + (fe.msgFor("cron_expr") ? " has-error" : "")}><label for="s-cron">${t("schedules.cronLabel")} <span class="req">*</span></label>
        <input id="s-cron" class="mono" value=${cron} onInput=${(e) => setCron(e.target.value)}
          aria-invalid=${fe.msgFor("cron_expr") ? "true" : undefined} aria-describedby=${fe.msgFor("cron_expr") ? fieldErrorId("cron_expr") : undefined} placeholder="0 21 * * *" />
        ${fe.msgFor("cron_expr") ? html`<div id=${fieldErrorId("cron_expr")} class="error small" role="alert">${fe.msgFor("cron_expr")}</div>` : null}
        ${preview === null ? null : preview.error ? html`<div class="error small">${t("schedules.cronInvalid")}</div>`
          : html`<div class="preview-out small"><b>${t("schedules.nextN", { n: preview.next.length })}</b> (${preview.tz}):
            <ul class="cron-next">${preview.next.map((ts) => html`<li key=${ts}>${fmtDateTime(ts, { tz: preview.tz })}</li>`)}</ul></div>`}</div>

      <div class=${"field" + (fe.msgFor("template_type") ? " has-error" : "")}><label for="s-tmpl">${t("schedules.templateTypeLabel")} <span class="req">*</span></label>
        <input id="s-tmpl" list="sched-tmpls" value=${templateType} onInput=${(e) => setTemplateType(e.target.value)}
          aria-invalid=${fe.msgFor("template_type") ? "true" : undefined} aria-describedby=${fe.msgFor("template_type") ? fieldErrorId("template_type") : undefined} placeholder=${t("schedules.templatePlaceholder")} />
        <datalist id="sched-tmpls">${templates.map((tp) => html`<option key=${tp} value=${tp}></option>`)}</datalist>
        ${templatesErr ? html`<div class="muted small">${t("schedules.tmplSuggestFailed")} <button class="btn sm ghost" onClick=${onReloadTemplates}>${t("common.retry")}</button></div>` : null}
        ${fe.msgFor("template_type") ? html`<div id=${fieldErrorId("template_type")} class="error small" role="alert">${fe.msgFor("template_type")}</div>` : null}</div>

      <div class="field"><label for="s-ctx">${t("schedules.contextLabel")}</label><textarea id="s-ctx" rows="3" class="mono" value=${ctxText} onInput=${(e) => setCtxText(e.target.value)} ...${fe.attrs("context")}></textarea>
        <${FieldMsg} fe=${fe} name="context" /></div>
      <div class="field"><label class="chk"><input type="checkbox" checked=${enabled} onChange=${(e) => setEnabled(e.target.checked)} /> ${t("schedules.enabledLabel")}</label></div>

      <div class="editor-actions">
        <button class="btn primary" onClick=${save} disabled=${busy}>${isNew ? t("schedules.create") : t("schedules.save")}</button>
        ${!isNew ? html`<button class="btn" onClick=${test} disabled=${busy || acting}>${t("schedules.testFire")}</button>
          <span class="spacer"></span><button class="btn danger" onClick=${() => setConfirmDel(true)} disabled=${busy}>${t("schedules.deleteBtn")}</button>` : null}
      </div>
    </div>
    <${DangerConfirm} open=${confirmDel} token=${schedule.name} title=${t("schedules.deleteTitle", { name: schedule.name })} busy=${busy}
      onConfirm=${doDelete} onClose=${() => setConfirmDel(false)} />
  </${Drawer}>`;
}
