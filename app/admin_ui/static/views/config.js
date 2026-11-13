// Config (phase F7): YAML export (with secret masking), validate, and a
// guarded apply (type APPLY to commit).
import { html, useState, useRef } from "../lib/h.js";
import { request } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { Json } from "../lib/ui.js";
import { t } from "../lib/i18n.js";

export function ConfigView() {
  const [mask, setMask] = useState(true);
  const [exported, setExported] = useState(null);
  const [yaml, setYaml] = useState("");
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [applyText, setApplyText] = useState("");
  // UX-009: a plan is only valid for the exact text it was validated against.
  // `validatedYaml` records that revision; `yamlRef` lets the async validate
  // response tell whether the text changed while it was in flight.
  const [validatedYaml, setValidatedYaml] = useState(null);
  const yamlRef = useRef("");
  yamlRef.current = yaml;

  async function doExport() {
    setBusy(true);
    try {
      const text = await request("GET", "/v1/config/export", { query: { mask_secrets: mask } });
      setExported(text);
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }
  function download() {
    const blob = new Blob([exported], { type: "application/yaml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "alertd-config.yaml"; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  async function validate() {
    const rev = yaml;
    setPlan(null); setValidatedYaml(null); setBusy(true);
    try {
      const r = await request("POST", "/v1/config/validate", { body: rev, raw: "application/yaml" });
      // Discard a stale response: if the text changed while validate was in
      // flight, the plan no longer describes what the editor holds (UX-009).
      if (yamlRef.current === rev) { setPlan(r); setValidatedYaml(rev); }
    }
    catch (e) { toast.error(e); } finally { setBusy(false); }
  }
  async function apply() {
    // Only import the exact revision that was validated and approved.
    if (applyText !== "APPLY" || validatedYaml !== yaml) return;
    setBusy(true);
    try {
      const r = await request("POST", "/v1/config/import", { body: yaml, raw: "application/yaml", query: { apply: true } });
      setPlan(r);
      if (r.applied) { toast.ok(t("config.toastApplied")); setApplyText(""); }
      else toast.error(t("config.toastNotApplied"));
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  const planOk = plan && plan.ok && validatedYaml === yaml;

  return html`<div>
    <div class="page-head"><div><h1>${t("config.title")}</h1><p class="muted">${t("config.subtitle")}</p></div></div>

    <div class="grid" style="grid-template-columns: 1fr; gap:14px">
      <div class="card">
        <h2>${t("config.exportHeading")}</h2>
        <label class="chk"><input type="checkbox" checked=${mask} onChange=${(e) => setMask(e.target.checked)} /> ${t("config.maskSecrets")}</label>
        <div class="form-actions" style="margin-top:10px">
          <button class="btn primary" onClick=${doExport} disabled=${busy}>${t("config.exportBtn")}</button>
          ${exported ? html`<button class="btn" onClick=${download}>${t("config.download")}</button>` : null}
        </div>
        ${exported ? html`<pre class="json" style="margin-top:10px; max-height:300px">${exported}</pre>` : null}
      </div>

      <div class="card">
        <h2>${t("config.validateImportHeading")}</h2>
        <p class="muted small">${t("config.validateHelp")}</p>
        <textarea rows="10" class="mono" value=${yaml} onInput=${(e) => { setYaml(e.target.value); setPlan(null); setApplyText(""); }} spellcheck="false" placeholder="templates:\n  - type: …"></textarea>
        <div class="form-actions" style="margin-top:10px">
          <button class="btn" onClick=${validate} disabled=${busy || !yaml.trim()}>${t("config.validateBtn")}</button>
          <span class="spacer"></span>
          ${planOk ? html`
            <input placeholder=${t("config.applyPlaceholder")} value=${applyText} onInput=${(e) => setApplyText(e.target.value)} style="width:auto" />
            <button class="btn danger" onClick=${apply} disabled=${busy || applyText !== "APPLY"}>${t("config.applyBtn")}</button>` : null}
        </div>

        ${plan ? html`<div class="result" style="margin-top:12px">
          <b>${t("config.planLabel")}</b> ${plan.ok ? html`<span class="badge ok plain">${t("config.planOk")}</span>` : html`<span class="badge critical plain">${t("config.planHasErrors")}</span>`}
          ${plan.applied ? html` <span class="badge ok plain">${t("config.planApplied")}</span>` : null}
          ${(plan.errors || []).length ? html`<div class="small"><b class="warn-text">${t("config.errorsLabel")}</b><ul>${plan.errors.map((e, i) => html`<li key=${i} class="error small">${typeof e === "string" ? e : JSON.stringify(e)}</li>`)}</ul></div>` : null}
          ${(plan.warnings || []).length ? html`<div class="small"><b>${t("config.warningsLabel")}</b><ul>${plan.warnings.map((w, i) => html`<li key=${i} class="small muted">${typeof w === "string" ? w : JSON.stringify(w)}</li>`)}</ul></div>` : null}
          <${Json} value=${plan} />
        </div>` : null}
      </div>
    </div>
  </div>`;
}
