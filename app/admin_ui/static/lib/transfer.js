// Per-section export and item-by-item import, shared by Templates, Rules and
// Variables (docs/ADMIN_UI.md, "Import / export").
//
//   <TransferMenu section="rules" shownNames=[…] filtered=bool onImported=reload />
//
// Export uses GET /v1/config/export?sections=…&names=… (secrets masked).
// Import is a three-step Drawer: pick / paste a YAML pack → preview every item
// (POST /v1/config/import/preview: new / identical / differs + changed fields)
// and choose overwrite / skip / copy → apply (POST /v1/config/import/apply).
// Existing items that differ default to "skip": nothing is overwritten without
// an explicit choice. A new route to a template that already exists
// (`existing_template`) adds a channel to the user's routing: the review says
// so, and a pack install skips it unless chosen (the server's `default`).
import { html, useState, useRef } from "./h.js";
import { request, api } from "./api.js";
import { useDialog } from "./dialog.js";
import { toast } from "./toast.js";
import { Drawer } from "./ui.js";
import { t } from "./i18n.js";

const NO_COPY = new Set(["routes"]);

function stamp() {
  return new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
}

export async function downloadPack(query, name) {
  const text = await request("GET", "/v1/config/export", { query: { mask_secrets: true, ...query } });
  const blob = new Blob([text], { type: "application/yaml" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${name}-${stamp()}.yaml`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  return text;
}

function MenuPanel({ id, onClose, children }) {
  const ref = useRef(null);
  useDialog(true, onClose, ref);   // Escape closes the panel, focus returns to the toggle
  return html`<div class="menu-panel" id=${id} ref=${ref} role="dialog" aria-label=${t("transfer.menuAria")}>${children}</div>`;
}

export function TransferMenu({ section, shownNames = [], filtered = false, onImported }) {
  const [open, setOpen] = useState(false);
  const [withDeps, setWithDeps] = useState(true);
  const [importing, setImporting] = useState(false);
  const [busy, setBusy] = useState(false);
  const label = t(`transfer.section.${section}`);

  async function run(query, name) {
    setBusy(true);
    try {
      await downloadPack({ sections: section, ...query, ...(section === "rules" && withDeps ? { with_dependencies: true } : {}) }, name);
      setOpen(false);
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  return html`<div class="menu-wrap">
    <button class="btn" aria-expanded=${open} aria-controls=${`xfer-${section}`} onClick=${() => setOpen(!open)}>${t("transfer.actions")} ▾</button>
    ${open ? html`<${MenuPanel} id=${`xfer-${section}`} onClose=${() => setOpen(false)}>
      <button class="menu-item" disabled=${busy} onClick=${() => run({}, `klopot-${section}`)}>${t("transfer.exportAll", { what: label })}</button>
      ${filtered && shownNames.length ? html`<button class="menu-item" disabled=${busy}
          onClick=${() => run({ names: shownNames.join(",") }, `klopot-${section}-filtered`)}>${t("transfer.exportShown", { count: shownNames.length })}</button>` : null}
      ${section === "rules" ? html`<label class="chk menu-item"><input type="checkbox" checked=${withDeps} onChange=${(e) => setWithDeps(e.target.checked)} /> ${t("transfer.withDeps")}</label>` : null}
      <hr />
      <button class="menu-item" onClick=${() => { setOpen(false); setImporting(true); }}>${t("transfer.import")}</button>
    </${MenuPanel}>` : null}
    ${importing ? html`<${ImportWizard} onClose=${() => setImporting(false)} onDone=${() => { setImporting(false); onImported?.(); }} />` : null}
  </div>`;
}

// ── Import wizard ─────────────────────────────────────────────────

const actionsFor = (item) => {
  if (item.status === "new") return ["import", "skip"];
  if (item.status === "differs") return NO_COPY.has(item.section) ? ["skip", "overwrite"] : ["skip", "overwrite", "copy"];
  return [];
};

function fmtValue(v) {
  if (v === null || v === undefined) return "—";
  return typeof v === "object" ? JSON.stringify(v) : String(v);
}

// Per-item decisions over a preview: new items follow the server's default
// (import — or skip, for a pack's route to an existing template), differing
// ones the bulk choice, unless set one by one. Only decisions that differ from
// what the server does by itself are sent. Shared by the import wizard and
// the Packs page.
export function useDecisions(preview) {
  const [choice, setChoice] = useState({});           // "<section>:<key>" → action
  const [bulk, setBulk] = useState("skip");           // default for existing items that differ
  const decisionOf = (item) => {
    const k = `${item.section}:${item.key}`;
    if (choice[k]) return choice[k];
    if (item.status === "new") return item.default || "import";
    if (item.status === "differs") return NO_COPY.has(item.section) && bulk === "copy" ? "skip" : bulk;
    return null;
  };
  const payload = () => {
    const decisions = {};
    for (const item of preview?.items || []) {
      const d = decisionOf(item);
      const serverDefault = item.status === "new" ? (item.default || "import") : null;
      if (d && d !== serverDefault) decisions[`${item.section}:${item.key}`] = d;
    }
    return { decisions, default_existing: bulk === "copy" ? "skip" : bulk };
  };
  return { choice, setChoice, bulk, setBulk, decisionOf, payload, reset: () => setChoice({}) };
}

// What apply will do with the current choices — the preview's counts say how
// the file differs from this instance, this says what Install / Apply changes.
export function planOf(items, dec) {
  const plan = { create: 0, overwrite: 0, copy: 0, skip: 0 };
  for (const item of items) {
    const d = dec.decisionOf(item);
    if (!d) continue;                                   // identical: nothing to do
    if (d === "import") plan.create++;
    else if (d === "overwrite") plan.overwrite++;
    else if (d === "copy") plan.copy++;
    else plan.skip++;
  }
  return plan;
}

// The preview body: errors, warnings, counts, the bulk choice and one table
// per section with each item's status, changed fields and action.
// `applyLabel` names the button that writes (nothing is saved before it).
export function ImportReview({ preview, dec, applyLabel }) {
  const items = preview.items || [];
  const sections = [...new Set(items.map((i) => i.section))];
  const onExisting = items.filter((i) => i.existing_template);
  const skippedByDefault = onExisting.some((i) => i.default === "skip");
  return html`
    ${preview.errors.length ? html`<div class="alert crit"><b>${t("transfer.errors")}</b><ul>${preview.errors.map((e, i) => html`<li key=${i}>${e}</li>`)}</ul>
      <p class="small">${t("transfer.errorsHint")}</p></div>` : null}
    ${preview.warnings.length ? html`<div class="alert warn"><b>${t("transfer.warnings")}</b><ul>${preview.warnings.map((w, i) => html`<li key=${i}>${w}</li>`)}</ul></div>` : null}
    <p class="muted">${t("transfer.counts", preview.counts)}</p>
    <p class="small muted">${t("transfer.previewOnly", { button: applyLabel || t("transfer.apply") })}</p>
    ${onExisting.length ? html`<div class="alert" role="note">${t(skippedByDefault ? "transfer.existingRoutesSkipped" : "transfer.existingRoutesAdded", { count: onExisting.length })}</div>` : null}
    ${preview.counts.differs ? html`<div class="field"><label for="imp-bulk">${t("transfer.bulkLabel")}</label>
      <select id="imp-bulk" value=${dec.bulk} onChange=${(e) => dec.setBulk(e.target.value)}>
        ${["skip", "overwrite", "copy"].map((a) => html`<option key=${a} value=${a}>${t(`transfer.action.${a}`)}</option>`)}</select>
      <div class="hint">${t("transfer.bulkHint")}</div></div>` : null}
    ${sections.map((s) => html`<section key=${s} class="import-section">
      <h3>${t(`transfer.section.${s}`)}</h3>
      <div class="scroll-x" tabindex="0"><table class="tbl compact"><thead><tr><th>${t("transfer.colItem")}</th><th>${t("transfer.colStatus")}</th><th>${t("transfer.colChanges")}</th><th>${t("transfer.colAction")}</th></tr></thead>
      <tbody>${items.filter((i) => i.section === s).map((i) => html`<tr key=${i.key}>
        <td class="mono small">${i.key}${i.existing_template ? html`<div class="hint">${t("transfer.existingTemplate")}</div>` : null}</td>
        <td><span class=${"chip " + (i.status === "differs" ? "warn" : i.status === "new" ? "tag" : "")}>${t(`transfer.status.${i.status}`)}</span></td>
        <td class="small">${i.changes.length ? html`<details><summary>${t("transfer.changeCount", { count: i.changes.length })}</summary>
          <ul class="diff">${i.changes.map((c) => html`<li key=${c.field}><b>${c.field}</b>: <span class="mono">${fmtValue(c.current)}</span> → <span class="mono">${fmtValue(c.incoming)}</span></li>`)}</ul></details>` : "—"}</td>
        <td>${actionsFor(i).length ? html`<select aria-label=${t("transfer.actionAria", { item: i.key })} value=${dec.decisionOf(i)}
            onChange=${(e) => dec.setChoice((c) => ({ ...c, [`${i.section}:${i.key}`]: e.target.value }))}>
            ${actionsFor(i).map((a) => html`<option key=${a} value=${a}>${t(`transfer.action.${a}`)}</option>`)}</select>`
          : html`<span class="muted small">${t("transfer.noChange")}</span>`}</td>
      </tr>`)}</tbody></table></div></section>`)}
    <p class="import-plan" role="status"><b>${t("transfer.planTitle", { button: applyLabel || t("transfer.apply") })}</b> ${t("transfer.plan", planOf(items, dec))}</p>`;
}

// What an apply returned, as a short summary (+ the renamed copies).
export function ImportDone({ result, onDone, title }) {
  return html`<div class="alert">
    <b>${title || t("transfer.doneTitle")}</b>
    <p>${t("transfer.doneSummary", { created: result.created.length, overwritten: result.overwritten.length, copied: Object.keys(result.copied).length, skipped: result.skipped.length })}</p>
    ${Object.entries(result.copied).map(([from, to]) => html`<div key=${from} class="small mono">${from} → ${to}</div>`)}
    <div class="form-actions"><button class="btn primary" onClick=${onDone}>${t("transfer.close")}</button></div>
  </div>`;
}

export function ImportWizard({ onClose, onDone }) {
  const [text, setText] = useState("");
  const [preview, setPreview] = useState(null);       // response of /preview for `previewedText`
  const [previewedText, setPreviewedText] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const dec = useDecisions(preview);

  async function readFile(e) {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    setText(await f.text()); setPreview(null); setResult(null);
  }

  async function doPreview() {
    setBusy(true); setResult(null);
    try {
      const r = await request("POST", "/v1/config/import/preview", { body: text, raw: "application/yaml" });
      setPreview(r); setPreviewedText(text); dec.reset();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  async function doApply() {
    if (previewedText !== text) return;
    setBusy(true);
    try {
      const r = await api.post("/v1/config/import/apply", { yaml: text, ...dec.payload() });
      setResult(r);
      if (r.applied) toast.ok(t("transfer.applied", { created: r.created.length, overwritten: r.overwritten.length, copied: Object.keys(r.copied).length }));
      else toast.error(t("transfer.notApplied"));
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  const stale = preview && previewedText !== text;

  return html`<${Drawer} open=${true} width=${820} title=${t("transfer.importTitle")} onClose=${onClose} dirty=${!!text && !result?.applied}>
    <div class="editor">
      ${result?.applied ? html`<${ImportDone} result=${result} onDone=${onDone} />` : html`
      <div class="field"><label for="imp-file">${t("transfer.fileLabel")}</label>
        <input id="imp-file" type="file" accept=".yaml,.yml,application/yaml,text/yaml" onChange=${readFile} /></div>
      <div class="field"><label for="imp-text">${t("transfer.pasteLabel")}</label>
        <textarea id="imp-text" rows="6" class="mono" spellcheck="false" value=${text}
          onInput=${(e) => { setText(e.target.value); setResult(null); }}></textarea></div>
      <div class="form-actions"><button class="btn" disabled=${busy || !text.trim()} onClick=${doPreview}>${t("transfer.preview")}</button></div>

      ${stale ? html`<div class="alert warn">${t("transfer.stalePreview")}</div>` : null}
      ${preview ? html`
        <${ImportReview} preview=${preview} dec=${dec} />
        ${result && !result.applied ? html`<div class="alert crit"><b>${t("transfer.notApplied")}</b><ul>${(result.errors || []).map((e, i) => html`<li key=${i}>${e}</li>`)}</ul></div>` : null}
        <div class="form-actions">
          <button class="btn primary" disabled=${busy || stale || !(preview.items || []).length} onClick=${doApply}>${t("transfer.apply")}</button>
        </div>` : null}`}
    </div>
  </${Drawer}>`;
}
