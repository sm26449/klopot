// API reference: every /v1 operation of this instance, read from
// /openapi.json (login-gated unless public docs are enabled — S-12), grouped
// by resource, with the key scope each call needs (x-required-scope), its
// parameters, body fields, responses and a ready-to-paste curl command.
// Swagger UI (/docs) and ReDoc (/redoc) are linked for "try it out".
import { html, useState } from "../lib/h.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { useLoader } from "../lib/loader.js";
import { Spinner, Empty, ErrorState } from "../lib/ui.js";
import { t } from "../lib/i18n.js";

const METHODS = ["get", "post", "put", "patch", "delete"];
const REF_PREFIX = "#/components/schemas/";

function resolve(spec, schema) {
  let s = schema || {};
  for (let i = 0; i < 5 && s.$ref && s.$ref.startsWith(REF_PREFIX); i += 1) {
    s = spec.components?.schemas?.[s.$ref.slice(REF_PREFIX.length)] || {};
  }
  return s;
}

export function typeLabel(schema) {
  if (!schema) return "";
  if (schema.$ref) return schema.$ref.split("/").pop();
  if (schema.anyOf || schema.oneOf) {
    return (schema.anyOf || schema.oneOf).filter((s) => s.type !== "null").map(typeLabel).join(" | ");
  }
  if (schema.type === "array") return `${typeLabel(schema.items) || "any"}[]`;
  if (schema.enum) return schema.enum.map((v) => JSON.stringify(v)).join(" | ");
  return schema.type || "any";
}

function placeholder(spec, schema) {
  const s = resolve(spec, schema);
  if (s.example !== undefined) return s.example;
  if (s.default !== undefined && s.default !== null) return s.default;
  const type = s.type || (s.anyOf || []).map((x) => x.type).find((x) => x && x !== "null");
  if (type === "integer" || type === "number") return 0;
  if (type === "boolean") return false;
  if (type === "array") return [];
  if (type === "object") return {};
  return "…";
}

// Flatten the spec into [{tag, method, path, op}], keeping spec order.
export function operations(spec) {
  const out = [];
  for (const [path, item] of Object.entries(spec?.paths || {})) {
    for (const method of METHODS) {
      const op = item[method];
      if (op) out.push({ tag: (op.tags || ["other"])[0], method, path, op });
    }
  }
  return out;
}

export function bodySchema(spec, op) {
  const content = op.requestBody?.content || {};
  const media = content["application/json"] || Object.values(content)[0];
  return media ? resolve(spec, media.schema) : null;
}

export function curlFor(spec, { method, path, op }, origin) {
  const lines = [`curl -X ${method.toUpperCase()} '${origin}${path}'`];
  if (op["x-required-scope"] !== "session" && op.security) lines.push(`  -H "X-API-Key: $KLOPOT_KEY"`);
  const body = bodySchema(spec, op);
  if (body && body.properties) {
    const example = {};
    for (const name of body.required || []) example[name] = placeholder(spec, body.properties[name]);
    lines.push(`  -H 'Content-Type: application/json'`);
    lines.push(`  -d '${JSON.stringify(example)}'`);
  }
  return lines.join(" \\\n");
}

function scopeLabel(scope) {
  if (scope === undefined) return t("api.scopeNone");
  if (scope === "session") return t("api.scopeSession");
  return t("api.scope", { scope: Array.isArray(scope) ? scope.join(", ") : scope });
}

function Fields({ rows }) {
  // Scrolls inside its own box on a phone (keyboard-focusable, see .scroll-x).
  return html`<div class="scroll-x" tabindex="0"><table class="tbl compact"><thead><tr>
      <th>${t("api.colName")}</th><th>${t("api.colType")}</th><th>${t("api.colRequired")}</th><th>${t("api.colDescription")}</th>
    </tr></thead><tbody>${rows.map((r) => html`<tr key=${r.name}>
      <td class="mono small">${r.name}${r.where ? html` <span class="muted">(${r.where})</span>` : null}</td>
      <td class="mono small">${r.type}</td>
      <td>${r.required ? t("api.yes") : ""}</td>
      <td class="small">${r.description || ""}</td>
    </tr>`)}</tbody></table></div>`;
}

function Operation({ spec, entry }) {
  const { method, path, op } = entry;
  const scope = op["x-required-scope"];
  const params = (op.parameters || []).map((p) => ({
    name: p.name, where: p.in, type: typeLabel(p.schema), required: !!p.required, description: p.description,
  }));
  const body = bodySchema(spec, op);
  const bodyRows = body?.properties ? Object.entries(body.properties).map(([name, s]) => ({
    name, type: typeLabel(s), required: (body.required || []).includes(name), description: resolve(spec, s).description || s.description,
  })) : [];
  const curl = curlFor(spec, entry, window.location.origin);
  async function copy() {
    try { await navigator.clipboard.writeText(curl); toast.ok(t("api.copied")); } catch { toast.error(t("api.copyFailed")); }
  }
  return html`<details class="api-op">
    <summary>
      <span class=${`api-method ${method}`}>${method.toUpperCase()}</span>
      <span class="mono">${path}</span>
      <span class="api-summary muted">${op.summary || ""}</span>
      <span class="badge plain small">${scopeLabel(scope)}</span>
    </summary>
    <div class="api-body">
      ${op.description ? html`<p class="api-desc">${op.description}</p>` : null}
      ${params.length ? html`<h3>${t("api.parameters")}</h3><${Fields} rows=${params} />` : null}
      ${bodyRows.length ? html`<h3>${t("api.body")}</h3><${Fields} rows=${bodyRows} />` : null}
      <h3>${t("api.responses")}</h3>
      <ul class="api-responses">${Object.entries(op.responses || {}).map(([code, r]) =>
        html`<li key=${code}><span class="mono">${code}</span> ${r.description || ""}</li>`)}</ul>
      <h3>${t("api.example")}</h3>
      <pre class="api-curl mono small">${curl}</pre>
      <button class="btn" onClick=${copy}>${t("api.copyCurl")}</button>
    </div>
  </details>`;
}

export function ApiView() {
  const [spec, , reload, error] = useLoader((signal) => api.get("/openapi.json", undefined, { signal }), []);
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");

  const all = spec ? operations(spec) : [];
  const tags = [...new Set(all.map((o) => o.tag))];
  const q = search.trim().toLowerCase();
  const shown = all.filter((o) => (!tag || o.tag === tag)
    && (!q || o.path.toLowerCase().includes(q) || (o.op.summary || "").toLowerCase().includes(q)));
  const groups = tags.map((g) => [g, shown.filter((o) => o.tag === g)]).filter(([, ops]) => ops.length);

  return html`<div>
    <div class="page-head">
      <div><h1>${t("api.title")}</h1>
        <p class="muted">${t("api.intro")} <a href="#/api-keys">${t("api.keysLink")}</a></p></div>
      <div class="actions">
        <a class="btn" href="/docs" target="_blank" rel="noopener">${t("api.swagger")}</a>
        <a class="btn" href="/redoc" target="_blank" rel="noopener">ReDoc</a>
        <a class="btn" href="/openapi.json" download="klopot-openapi.json">openapi.json</a>
      </div>
    </div>

    <div class="card filters">
      <input class="grow" aria-label=${t("api.searchPlaceholder")} placeholder=${t("api.searchPlaceholder")} value=${search} onInput=${(e) => setSearch(e.target.value)} />
      <select aria-label=${t("api.resource")} value=${tag} onChange=${(e) => setTag(e.target.value)}>
        <option value="">${t("api.allResources")}</option>
        ${tags.map((g) => html`<option key=${g} value=${g}>${g}</option>`)}
      </select>
    </div>

    ${error && !spec ? html`<${ErrorState} error=${error} onRetry=${reload} />`
      : !spec ? html`<${Spinner} />`
      : groups.length === 0 ? html`<${Empty} label=${t("api.empty")} />`
      : groups.map(([g, ops]) => html`<section key=${g} class="card api-group">
          <h2>${g} <span class="muted small">${ops.length}</span></h2>
          ${ops.map((o) => html`<${Operation} key=${o.method + o.path} spec=${spec} entry=${o} />`)}
        </section>`)}
  </div>`;
}
