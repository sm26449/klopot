// Packs (docs/PACKS.md): the built-in catalog, installing a pack (yours or
// from the catalog) with its parameters, and exporting part of the
// configuration as a pack.
//
// Install = parameters → POST /v1/packs/preview → the same per-item review as
// config import (lib/transfer.js ImportReview) → POST /v1/packs/apply.
import { html, useEffect, useState } from "../lib/h.js";
import { api, getAll } from "../lib/api.js";
import { lookupFailed } from "../lib/lookup.js";
import { toast } from "../lib/toast.js";
import { Drawer, ErrorState, Spinner } from "../lib/ui.js";
import { t, lt } from "../lib/i18n.js";
import { ImportReview, ImportDone, useDecisions, downloadPack } from "../lib/transfer.js";
import { fieldErrorId } from "../lib/form.js";

const SECTIONS = ["inputs", "variables", "templates", "channels", "rules", "routes", "schedules"];

function countsText(counts) {
  return SECTIONS.filter((s) => counts?.[s]).map((s) => `${counts[s]} ${t(`transfer.section.${s}`)}`).join(" · ");
}

export function PacksView() {
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState(null);
  const [channels, setChannels] = useState([]);
  const [installing, setInstalling] = useState(null);   // {source, summary}
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(false);

  async function load() {
    setError(null);
    try { setCatalog((await api.get("/v1/packs")).items); } catch (e) { setError(e); }
  }
  async function loadChannels() {
    // On failure the field falls back to free text — and the operator is told.
    try { setChannels((await getAll("/v1/channels")).items.map((c) => c.name).sort()); } catch (e) { lookupFailed(e); }
  }
  useEffect(() => { load(); loadChannels(); }, []);

  return html`<div>
    <div class="page-head">
      <div><h1>${t("packs.title")}</h1><p class="muted">${t("packs.subtitle")}</p></div>
      <div class="actions">
        <button class="btn" onClick=${() => setExporting(true)}>${t("packs.createBtn")}</button>
        <button class="btn primary" onClick=${() => setUploading(true)}>${t("packs.installFileBtn")}</button>
      </div>
    </div>

    ${error ? html`<${ErrorState} error=${error} onRetry=${load} />` : catalog === null ? html`<${Spinner} />` : html`
      <h2 class="section-title">${t("packs.catalogHeading")}</h2>
      <div class="cards pack-cards">${catalog.map((p) => html`<article class="card pack-card" key=${p.id}>
        <h3>${lt(p.name)}</h3>
        <p class="small">${lt(p.description)}</p>
        <p class="small muted">${countsText(p.counts)}</p>
        <div class="pack-foot">
          <span>${(p.tags || []).map((tag) => html`<span key=${tag} class="chip tag">${tag}</span>`)}</span>
          <button class="btn primary sm" onClick=${() => setInstalling({ source: { pack_id: p.id }, summary: p })}
            aria-label=${t("packs.installAria", { name: lt(p.name) })}>${t("packs.install")}</button>
        </div>
      </article>`)}</div>`}

    ${installing ? html`<${InstallDrawer} ...${installing} channels=${channels}
        onClose=${() => setInstalling(null)} onDone=${() => { setInstalling(null); loadChannels(); }} />` : null}
    ${uploading ? html`<${UploadDrawer} onClose=${() => setUploading(false)}
        onReady=${(source, summary) => { setUploading(false); setInstalling({ source, summary }); }} />` : null}
    ${exporting ? html`<${ExportDrawer} onClose=${() => setExporting(false)} />` : null}
  </div>`;
}

// ── Installing ─────────────────────────────────────────────────────

function initialParams(summary) {
  return Object.fromEntries((summary.parameters || []).map((p) => [p.name, p.default ?? (p.type === "boolean" ? false : "")]));
}

// "parameter threshold: expected a number" → { threshold: "expected a number" }
function paramErrors(errors) {
  const out = {};
  for (const e of errors || []) {
    const m = /^parameter ([a-z][a-z0-9_]*): (.*)$/.exec(e);
    if (m) out[m[1]] = m[2] === "required" ? t("common.required") : m[2];
  }
  return out;
}

function ParamField({ p, value, onInput, error, channels }) {
  const id = `pp-${p.name}`;
  const aria = error ? { "aria-invalid": "true", "aria-describedby": fieldErrorId(`pp_${p.name}`) } : {};
  const label = lt(p.label) || p.name;
  let control;
  if (p.type === "boolean") {
    return html`<div class="field"><label class="chk"><input id=${id} type="checkbox" checked=${!!value}
      onChange=${(e) => onInput(e.target.checked)} ...${aria} /> ${label}</label>
      ${p.description ? html`<div class="hint">${lt(p.description)}</div>` : null}</div>`;
  } else if (p.type === "channel" && channels.length) {
    const names = channels.includes(value) || !value ? channels : [value, ...channels];
    control = html`<select id=${id} value=${value} onChange=${(e) => onInput(e.target.value)} ...${aria}>
      ${names.map((c) => html`<option key=${c} value=${c}>${c}</option>`)}</select>`;
  } else if (p.type === "number" || p.type === "integer") {
    control = html`<input id=${id} type="number" step=${p.type === "integer" ? "1" : "any"} value=${value ?? ""}
      onInput=${(e) => onInput(e.target.value)} ...${aria} />`;
  } else {
    control = html`<input id=${id} class=${p.type === "env" ? "mono" : ""} value=${value ?? ""}
      onInput=${(e) => onInput(e.target.value)} ...${aria} />`;
  }
  return html`<div class=${"field" + (error ? " has-error" : "")}>
    <label for=${id}>${label}${p.required ? html` <span class="req">*</span>` : null}</label>
    ${control}
    ${p.description ? html`<div class="hint">${lt(p.description)}</div>` : p.type === "env" ? html`<div class="hint">${t("packs.envHint")}</div>` : null}
    ${error ? html`<div id=${fieldErrorId(`pp_${p.name}`)} class="error small">${error}</div>` : null}
  </div>`;
}

export function InstallDrawer({ source, summary, channels, onClose, onDone }) {
  const [params, setParams] = useState(() => initialParams(summary));
  const [preview, setPreview] = useState(null);
  const [previewedFor, setPreviewedFor] = useState(null);   // JSON of the params the preview used
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const dec = useDecisions(preview);
  const key = JSON.stringify(params);
  const stale = preview && previewedFor !== key;
  const fieldErr = preview && !preview.ok ? paramErrors(preview.errors) : {};
  const otherErrors = preview && !preview.ok ? preview.errors.filter((e) => !/^parameter /.test(e)) : [];

  async function doPreview() {
    setBusy(true); setResult(null);
    try {
      const r = await api.post("/v1/packs/preview", { ...source, params });
      setPreview(r); setPreviewedFor(key); dec.reset();
      if (Object.keys(paramErrors(r.errors)).length) document.getElementById(`pp-${Object.keys(paramErrors(r.errors))[0]}`)?.focus();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }
  async function doApply() {
    if (stale) return;
    setBusy(true);
    try {
      const r = await api.post("/v1/packs/apply", { ...source, params, ...dec.payload() });
      setResult(r);
      if (r.applied) toast.ok(t("packs.installed", { name: lt(summary.name) }));
      else toast.error(t("transfer.notApplied"));
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  return html`<${Drawer} open=${true} width=${820} title=${t("packs.installTitle", { name: lt(summary.name) || summary.id || "" })}
      onClose=${onClose} dirty=${!result?.applied && previewedFor !== null}>
    <div class="editor">
      ${result?.applied ? html`<${ImportDone} result=${result} onDone=${onDone} title=${t("packs.doneTitle")} />` : html`
        ${summary.description ? html`<p>${lt(summary.description)}</p>` : null}
        <p class="small muted">${countsText(summary.counts)}</p>
        ${(summary.parameters || []).length ? html`<fieldset class="gate">
          <legend>${t("packs.paramsLegend")}</legend>
          ${summary.parameters.map((p) => html`<${ParamField} key=${p.name} p=${p} value=${params[p.name]} channels=${channels}
              error=${fieldErr[p.name]} onInput=${(v) => setParams((cur) => ({ ...cur, [p.name]: v }))} />`)}
        </fieldset>` : html`<p class="muted small">${t("packs.noParams")}</p>`}
        <div class="form-actions"><button class="btn" disabled=${busy} onClick=${doPreview}>${t("transfer.preview")}</button></div>
        ${stale ? html`<div class="alert warn">${t("packs.stalePreview")}</div>` : null}
        ${preview && !preview.ok && !(preview.items || []).length
          ? (otherErrors.length ? html`<div class="alert crit"><b>${t("transfer.errors")}</b><ul>${otherErrors.map((e, i) => html`<li key=${i}>${e}</li>`)}</ul></div>` : null)
          : preview ? html`
            <${EnvStatus} env=${preview.env} />
            <${ImportReview} preview=${preview} dec=${dec} />
            ${result && !result.applied ? html`<div class="alert crit"><b>${t("transfer.notApplied")}</b><ul>${(result.errors || []).map((e, i) => html`<li key=${i}>${e}</li>`)}</ul></div>` : null}
            <div class="form-actions">
              <button class="btn primary" disabled=${busy || stale || !preview.ok} onClick=${doApply}>${t("packs.install")}</button>
            </div>` : null}`}
    </div>
  </${Drawer}>`;
}

// The secrets an `env` setting names: ready, or what to add and where. The pack
// installs either way; it starts working once the value is in Klopot.
function EnvStatus({ env }) {
  if (!env || !env.length) return null;
  const missing = env.filter((e) => !e.allowed || !e.set);
  return html`<div class=${"alert " + (missing.length ? "warn" : "")} role="status">
    <b>${missing.length ? t("packs.envMissingTitle") : t("packs.envReadyTitle")}</b>
    <ul>${env.map((e) => html`<li key=${e.param}><span class="mono">${e.name}</span> —
      ${!e.allowed ? t("packs.envNotAllowed") : !e.set ? html`${t("packs.envNotSet")} <code>${e.name}=…</code>` : t("packs.envOk")}</li>`)}</ul>
    ${missing.length ? html`<p class="small">${t("packs.envHowTo")}</p>` : null}
  </div>`;
}

function UploadDrawer({ onClose, onReady }) {
  const [text, setText] = useState("");
  const [errors, setErrors] = useState([]);
  const [busy, setBusy] = useState(false);

  async function readFile(e) {
    const f = e.target.files && e.target.files[0];
    if (f) setText(await f.text());
  }
  async function next() {
    setBusy(true); setErrors([]);
    try {
      const r = await api.post("/v1/packs/inspect", { yaml: text });
      if (!r.ok) setErrors(r.errors);
      else onReady({ yaml: text }, r);
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  return html`<${Drawer} open=${true} width=${720} title=${t("packs.installFileBtn")} onClose=${onClose} dirty=${!!text}>
    <div class="editor">
      <p class="muted small">${t("packs.uploadHelp")}</p>
      <div class="field"><label for="pk-file">${t("transfer.fileLabel")}</label>
        <input id="pk-file" type="file" accept=".yaml,.yml,application/yaml,text/yaml" onChange=${readFile} /></div>
      <div class="field"><label for="pk-text">${t("transfer.pasteLabel")}</label>
        <textarea id="pk-text" rows="8" class="mono" spellcheck="false" value=${text} onInput=${(e) => setText(e.target.value)}></textarea></div>
      ${errors.length ? html`<div class="alert crit"><b>${t("transfer.errors")}</b><ul>${errors.map((e, i) => html`<li key=${i}>${e}</li>`)}</ul></div>` : null}
      <div class="form-actions"><button class="btn primary" disabled=${busy || !text.trim()} onClick=${next}>${t("packs.next")}</button></div>
    </div>
  </${Drawer}>`;
}

// ── Exporting ──────────────────────────────────────────────────────

function ExportDrawer({ onClose }) {
  const [id, setId] = useState("my-pack");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [sections, setSections] = useState(() => new Set(["rules"]));
  const [names, setNames] = useState("");
  const [withDeps, setWithDeps] = useState(true);
  const [busy, setBusy] = useState(false);
  const idOk = /^[a-z][a-z0-9-]{1,63}$/.test(id);

  function toggle(s) { setSections((cur) => { const n = new Set(cur); n.has(s) ? n.delete(s) : n.add(s); return n; }); }
  async function run() {
    if (!idOk || !sections.size) return;
    setBusy(true);
    try {
      await downloadPack({
        pack_id: id, ...(name.trim() ? { pack_name: name.trim() } : {}), ...(description.trim() ? { pack_description: description.trim() } : {}),
        sections: [...sections].join(","), ...(names.trim() ? { names: names.split(",").map((n) => n.trim()).filter(Boolean).join(",") } : {}),
        with_dependencies: withDeps,
      }, id);
      toast.ok(t("packs.exported"));
      onClose();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  return html`<${Drawer} open=${true} width=${640} title=${t("packs.createTitle")} onClose=${onClose}>
    <div class="editor">
      <p class="muted small">${t("packs.createHelp")}</p>
      <div class="row2">
        <div class=${"field" + (idOk ? "" : " has-error")}><label for="px-id">${t("packs.idLabel")} <span class="req">*</span></label>
          <input id="px-id" class="mono" value=${id} onInput=${(e) => setId(e.target.value)}
            aria-invalid=${idOk ? "false" : "true"} aria-describedby="px-id-hint" />
          <div id="px-id-hint" class=${idOk ? "hint" : "error small"}>${t("packs.idHint")}</div></div>
        <div class="field"><label for="px-name">${t("packs.nameLabel")}</label>
          <input id="px-name" value=${name} onInput=${(e) => setName(e.target.value)} /></div>
      </div>
      <div class="field"><label for="px-desc">${t("packs.descriptionLabel")}</label>
        <textarea id="px-desc" rows="2" value=${description} onInput=${(e) => setDescription(e.target.value)}></textarea></div>
      <fieldset class="gate"><legend>${t("packs.sectionsLegend")}</legend>
        <div class="chk-grid">${SECTIONS.filter((s) => s !== "routes").map((s) => html`<label key=${s} class="chk">
          <input type="checkbox" checked=${sections.has(s)} onChange=${() => toggle(s)} /> ${t(`transfer.section.${s}`)}</label>`)}</div>
      </fieldset>
      <div class="field"><label for="px-names">${t("packs.namesLabel")}</label>
        <input id="px-names" class="mono" value=${names} onInput=${(e) => setNames(e.target.value)} placeholder="disk_full_rule, room_temp" />
        <div class="hint">${t("packs.namesHint")}</div></div>
      <label class="chk"><input type="checkbox" checked=${withDeps} onChange=${(e) => setWithDeps(e.target.checked)} /> ${t("packs.withDeps")}</label>
      <p class="hint">${t("packs.secretsNote")}</p>
      <div class="form-actions"><button class="btn primary" disabled=${busy || !idOk || !sections.size} onClick=${run}>${t("packs.download")}</button></div>
    </div>
  </${Drawer}>`;
}
