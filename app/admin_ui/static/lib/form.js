// Form controls generated from GET /v1/meta/kinds field descriptors.
// A descriptor is {name, type, required, secret, default, help, options?, ref_field?}.
import { html, useState, useRef, useEffect } from "./h.js";
import { parseJsonField } from "./json_field.js";
import { t } from "./i18n.js";

// ── Server-side validation errors (audit UX-018) ────────────────────
// A 422 carries pydantic errors as detail:[{loc, msg}]. Map each to a field
// path (dropping the "body" prefix) + message so an editor can show which field
// the server rejected, instead of a single opaque toast.
export function fieldErrorsFrom(e) {
  if (!e || e.status !== 422 || !Array.isArray(e.detail)) return null;
  const out = e.detail.map((d) => {
    const loc = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body") : [];
    return { field: loc.join(".") || "—", msg: d.msg || t("common.invalid") };
  });
  return out.length ? out : null;
}

// Last dotted segment of a pydantic field path: "config.port" → "port". A
// control is matched to its error by this segment, so a nested `config.<name>`
// error lands on the FieldInput named `<name>`.
function lastSeg(path) { const p = String(path).split("."); return p[p.length - 1]; }

// Stable id for a field's inline error element, so a control can point its
// aria-describedby at it.
export function fieldErrorId(name) { return "fe_" + String(name).replace(/[^\w-]/g, "_"); }

// Editor helper: holds the current field errors. `show(e)` returns true and
// stores them when `e` is a 422 field error (so the caller skips the toast),
// false otherwise. `clear()` before each save. `msgFor(name)` returns the
// server message for the control named `name` (matched on the last path
// segment), or null, so that specific control can be marked invalid.
export function useFieldErrors() {
  const [errors, setErrors] = useState(null);
  return {
    errors,
    clear: () => setErrors(null),
    show: (e) => { const fe = fieldErrorsFrom(e); if (fe) { setErrors(fe); return true; } return false; },
    msgFor: (name) => { const hit = (errors || []).find((x) => lastSeg(x.field) === name); return hit ? hit.msg : null; },
  };
}

// A focusable, announced summary of the server's field errors, shown at the top
// of an editor. Focus moves to it when it appears so a keyboard/SR user is told.
// Each entry is a button that moves focus to the offending control: `idFor`
// maps a field path to a control id (default: the FieldInput id `f_<segment>`),
// so a view with hand-written inputs can point each error at its own control.
export function FieldErrorSummary({ errors, idFor }) {
  const ref = useRef(null);
  useEffect(() => { if (errors && errors.length && ref.current) ref.current.focus(); }, [errors]);
  if (!errors || !errors.length) return null;
  const resolveId = idFor || ((f) => "f_" + lastSeg(f));
  function focusField(f) {
    const el = document.getElementById(resolveId(f));
    if (el) { el.focus(); if (typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "center" }); }
  }
  return html`<div class="field-error-summary" role="alert" tabindex="-1" ref=${ref}>
    <b>${t("common.fixFields")}</b>
    <ul>${errors.map((e, i) => html`<li key=${i}>
      <button type="button" class="link-btn" onClick=${() => focusField(e.field)}><span class="mono">${e.field}</span></button>: ${e.msg}
    </li>`)}</ul>
  </div>`;
}

// ── Field validity tracking (audit A24) ────────────────────────────
// A json field whose text is unparseable must not be saveable. Editors
// call ``useFieldValidity`` once and wire ``setValidity`` into each
// FieldInput's ``onValidity``; ``anyInvalid`` gates the Save button and
// ``focusFirst`` moves focus to the offending control on a blocked save.
export function useFieldValidity() {
  const [invalid, setInvalid] = useState({});
  function setValidity(name, ok) {
    setInvalid((m) => {
      if (ok) {
        if (!(name in m)) return m;
        const next = { ...m };
        delete next[name];
        return next;
      }
      if (m[name]) return m;
      return { ...m, [name]: true };
    });
  }
  const invalidNames = Object.keys(invalid);
  function focusFirst() {
    const el = invalidNames[0] && document.getElementById("f_" + invalidNames[0]);
    if (el) el.focus();
  }
  // Called when the field set changes (kind/source switch) so validity
  // flags for now-unmounted fields don't keep Save disabled forever.
  function reset() { setInvalid({}); }
  return { invalidNames, anyInvalid: invalidNames.length > 0, setValidity, focusFirst, reset };
}

// Seed a config object from a kind's/source's metadata field defaults, so the
// chosen policy is sent explicitly instead of relying on an omitted field
// matching the backend default (audit V16). Only non-null defaults of
// non-secret fields are seeded; secrets never carry a default value.
export function configDefaults(fields) {
  const out = {};
  for (const f of fields || []) {
    if (!f.secret && f.default != null) out[f.name] = f.default;
  }
  return out;
}

// ── Non-secret field ───────────────────────────────────────────────
// `value` is the current config value; `onInput(newValue)` reports edits.
// `onValidity(ok)` (optional) reports whether the current text is a valid
// value — only the json control can be invalid; everything else is always
// valid and never calls it.
export function FieldInput({ field, value, onInput, onValidity, error }) {
  const t = field.type;
  const id = "f_" + field.name;
  const errId = fieldErrorId(field.name);
  // When the server rejected this field (audit UX-018/R8), mark the control
  // aria-invalid and tie it to the inline message so a SR announces both.
  const aria = error ? { "aria-invalid": "true", "aria-describedby": errId } : {};
  const label = html`<label for=${id}>${field.name}${field.required ? html` <span class="req">*</span>` : null}</label>`;
  const hint = field.help ? html`<div class="hint">${field.help}</div>` : null;
  const errNode = error ? html`<div id=${errId} class="error small" role="alert">${error}</div>` : null;

  let control;
  if (t === "bool") {
    // Reflect the metadata default when the config hasn't set this field yet —
    // `!!undefined` is false, so a field defaulting to TRUE used to render
    // unchecked, hiding the effective policy and forcing a double-toggle to opt
    // out (audit V16). `value ?? field.default ?? false` shows the real default.
    const on = value ?? field.default ?? false;
    control = html`<label class="chk"><input id=${id} type="checkbox" checked=${!!on} ...${aria}
      onChange=${(e) => onInput(e.target.checked)} /> ${field.name}</label>`;
    return html`<div class=${"field" + (error ? " has-error" : "")}>${control}${hint}${errNode}</div>`;
  } else if (t === "select") {
    control = html`<select id=${id} value=${value ?? field.default ?? ""} ...${aria} onChange=${(e) => onInput(e.target.value)}>
      ${(field.options || []).map((o) => html`<option key=${o} value=${o}>${o === "" ? "—" : o}</option>`)}
    </select>`;
  } else if (t === "text") {
    control = html`<textarea id=${id} rows="3" value=${value ?? ""} ...${aria} onInput=${(e) => onInput(e.target.value)}></textarea>`;
  } else if (t === "json") {
    control = html`<${JsonInput} id=${id} value=${value} onInput=${onInput} onValidity=${onValidity} serverError=${error} />`;
  } else if (t === "int" || t === "float") {
    control = html`<input id=${id} type="number" step=${t === "float" ? "any" : "1"} value=${value ?? ""} ...${aria}
      onInput=${(e) => onInput(e.target.value === "" ? null : Number(e.target.value))} />`;
  } else {
    // string / topic / cron
    control = html`<input id=${id} type="text" value=${value ?? ""} ...${aria} onInput=${(e) => onInput(e.target.value)}
      placeholder=${field.default != null ? String(field.default) : ""} />`;
  }
  // json owns its own inline error element; others render the server message.
  const extra = t === "json" ? null : errNode;
  return html`<div class=${"field" + (error ? " has-error" : "")}>${label}${control}${hint}${extra}</div>`;
}

// JSON object/array editor — textarea, validated on each edit.
// On an unparseable edit we report ``onValidity(false)`` and deliberately
// do NOT call ``onInput`` — the parent keeps its last good value, but the
// editor blocks Save so that stale value can never be persisted behind a
// "saved" confirmation (audit A24).
function JsonInput({ id, value, onInput, onValidity, serverError }) {
  const [text, setText] = useState(() => (value == null ? "" : JSON.stringify(value, null, 2)));
  const [err, setErr] = useState(null);
  function change(v) {
    setText(v);
    const r = parseJsonField(v);
    if (r.ok) {
      setErr(null);
      onInput(r.value);
      onValidity?.(true);
    } else {
      setErr(r.error);
      onValidity?.(false);
    }
  }
  const errId = id + "-err";
  // A local parse error takes precedence; otherwise surface a server rejection
  // of this field (audit UX-018/R8), both tied to the control via describedby.
  const invalid = err ? `${t("common.invalidJson")}: ${err}` : serverError || null;
  return html`<div>
    <textarea id=${id} rows="3" class=${"mono" + (invalid ? " invalid" : "")} value=${text}
      aria-invalid=${invalid ? "true" : undefined} aria-describedby=${invalid ? errId : undefined}
      onInput=${(e) => change(e.target.value)} spellcheck="false"></textarea>
    ${invalid ? html`<div id=${errId} class="error small" role="alert">${invalid}</div>` : null}
  </div>`;
}

// ── Secret field ───────────────────────────────────────────────────
// `status` is the secret_fields_set entry: "literal" | "env:NAME" |
// "secret:NAME" | undefined (unset). `onChange(update)` reports one of:
//   null                      → keep stored value (omit from PATCH)
//   {clear:true}              → clear (send "")
//   {value:"..."}             → replace literal (send config[name])
//   {ref:"ENVNAME"}           → reference env var (send config[name_ref])
export function SecretField({ field, status, onChange }) {
  const [mode, setMode] = useState("keep");   // keep | value | ref | clear
  const set = status != null;

  function pick(m) {
    setMode(m);
    if (m === "keep") onChange(null);
    else if (m === "clear") onChange({ clear: true });
    else if (m === "value") onChange({ value: "" });
    else if (m === "ref") onChange({ ref: "" });
  }

  return html`<div class="field secret">
    <label>${field.name} <span class="muted small">(secret)</span></label>
    <div class="secret-state">
      ${set ? html`<span class="badge ok plain">${t("common.set")} · ${status}</span>` : html`<span class="badge plain">${t("common.notSet")}</span>`}
      ${mode === "keep" ? html`<button type="button" class="btn sm" onClick=${() => pick("value")}>${t("common.replace")}</button>
        <button type="button" class="btn sm ghost" onClick=${() => pick("ref")}>${t("common.useEnvRef")}</button>
        ${set ? html`<button type="button" class="btn sm ghost danger" onClick=${() => pick("clear")}>${t("common.clear")}</button>` : null}`
        : html`<button type="button" class="btn sm ghost" onClick=${() => pick("keep")}>${t("common.cancel")}</button>`}
    </div>
    ${mode === "value" ? html`<input type="password" autocomplete="new-password" placeholder=${t("common.newSecretValue")}
      onInput=${(e) => onChange({ value: e.target.value })} />` : null}
    ${mode === "ref" ? html`<input type="text" placeholder=${t("common.envVarName")}
      onInput=${(e) => onChange({ ref: e.target.value })} />
      <div class="hint">${t("common.envRefHint", { ref: field.ref_field })}</div>` : null}
    ${mode === "clear" ? html`<div class="hint">${t("common.clearSecretHint")}</div>` : null}
    ${field.help ? html`<div class="hint">${field.help}</div>` : null}
  </div>`;
}

// ── Tag input (multi-value with autocomplete) ─────────────────────
// `value` is an array of strings; `onChange(array)`; `options` feeds a datalist.
export function TagInput({ value, onChange, options = [], placeholder, inputId, ariaLabel }) {
  placeholder = placeholder ?? t("common.tagAdd");
  const [draft, setDraft] = useState("");
  const tags = value || [];
  function add(v) {
    const val = (v ?? draft).trim();
    if (val && !tags.includes(val)) onChange([...tags, val]);
    setDraft("");
  }
  function remove(tag) { onChange(tags.filter((x) => x !== tag)); }
  const listId = "dl_" + Math.random().toString(36).slice(2, 8);
  return html`<div class="taginput">
    <div class="tags">${tags.map((tag) => html`<span key=${tag} class="chip tag">${tag}
      <button type="button" class="x" onClick=${() => remove(tag)} aria-label=${t("common.removeTag", { tag })}>✕</button></span>`)}</div>
    <input id=${inputId} aria-label=${ariaLabel} list=${listId} value=${draft} placeholder=${placeholder}
      onInput=${(e) => setDraft(e.target.value)}
      onChange=${(e) => { if (options.includes(e.target.value)) add(e.target.value); }}
      onKeyDown=${(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
    <datalist id=${listId}>${options.filter((o) => !tags.includes(o)).map((o) => html`<option key=${o} value=${o}></option>`)}</datalist>
  </div>`;
}

// Apply collected secret edits onto a config object for PATCH/POST.
// `edits` is {fieldName: update} as emitted by SecretField.
export function applySecretEdits(config, fields, edits) {
  const out = { ...config };
  for (const f of fields.filter((x) => x.secret)) {
    const u = edits[f.name];
    if (!u) continue;                              // keep
    delete out[f.name]; delete out[f.ref_field];
    if (u.clear) { out[f.name] = ""; }
    else if (u.ref != null && u.ref !== "") { out[f.ref_field] = u.ref; }
    else if (u.value != null && u.value !== "") { out[f.name] = u.value; }
  }
  return out;
}
