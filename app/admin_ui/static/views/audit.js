// Audit (phase F7): paged action history with filters and a
// before/after diff drawer.
import { html, useState } from "../lib/h.js";
import { api } from "../lib/api.js";
import { useLoader } from "../lib/loader.js";
import { useUrlFilters } from "../lib/router.js";
import { toast } from "../lib/toast.js";
import { Drawer, Spinner, Empty, ErrorState, StaleBanner, Pager } from "../lib/ui.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import { t } from "../lib/i18n.js";

const LIMIT = 50;

export function AuditView({ query }) {
  // Filters AND the page offset live in the URL so they survive reload/back/
  // forward, and any filter change resets to page 1 (UX-015/R5).
  const [filters, setF, , offset, setOffset] = useUrlFilters("/audit", query, {
    action: "", resource_kind: "", resource_id: "", actor_name: "",
  });
  const [selected, setSelected] = useState(null);

  // Debounced + cancelable + generation-guarded (audit UX-008): fast typing no
  // longer fires a request per keystroke, and a slow earlier response can't
  // overwrite the rows for the current filter.
  const [data, , reload, error] = useLoader((signal) => {
    const q = { skip: offset, limit: LIMIT };
    for (const [k, v] of Object.entries(filters)) if (v) q[k] = v;
    return api.get("/v1/audit", q, { signal });
  }, [filters, offset]);

  const items = data?.items || [];

  return html`<div>
    <div class="page-head">
      <div><h1>${t("audit.title")}</h1><p class="muted">${t("audit.intro")}</p></div>
      <div class="actions"><button class="btn sm" onClick=${reload}>${t("audit.refresh")}</button></div>
    </div>

    <div class="card filters">
      <input placeholder=${t("audit.actionPlaceholder")} value=${filters.action} onInput=${(e) => setF("action", e.target.value)} />
      <input placeholder=${t("audit.resourceKindPlaceholder")} value=${filters.resource_kind} onInput=${(e) => setF("resource_kind", e.target.value)} />
      <input placeholder=${t("audit.resourceIdPlaceholder")} value=${filters.resource_id} onInput=${(e) => setF("resource_id", e.target.value)} />
      <input placeholder=${t("audit.actorPlaceholder")} value=${filters.actor_name} onInput=${(e) => setF("actor_name", e.target.value)} />
    </div>

    ${error && data ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
    <div class="card" style="margin-top:14px; padding:0">
      ${error && !data ? html`<${ErrorState} error=${error} onRetry=${reload} />` : data === null ? html`<${Spinner} />` : items.length === 0 ? html`<${Empty} label=${t("audit.empty")} />`
        : html`<table class="tbl"><thead><tr><th>${t("audit.colWhen")}</th><th>${t("audit.colActor")}</th><th>${t("audit.colAction")}</th><th>${t("audit.colResource")}</th></tr></thead>
          <tbody>${items.map((a) => html`<tr key=${a.id} onClick=${() => setSelected(a)} style="cursor:pointer">
            <td class="nowrap"><button type="button" class="cell-btn" title=${fmtDateTime(a.ts)}
                aria-label=${t("audit.viewEntry")} onClick=${(e) => { e.stopPropagation(); setSelected(a); }}>${fmtRelative(a.ts)}</button></td>
            <td><span class="badge plain">${a.actor_kind}</span> ${a.actor_name || ""}</td>
            <td class="mono small">${a.action}</td>
            <td class="small">${a.resource_kind || ""}${a.resource_id ? html` <span class="mono">${a.resource_id}</span>` : null}</td>
          </tr>`)}</tbody></table>`}
      ${data ? html`<div style="padding:10px 14px"><${Pager} offset=${data.offset} limit=${data.limit} total=${data.total} onPage=${setOffset} /></div>` : null}
    </div>

    ${selected ? html`<${AuditDrawer} entry=${selected} onClose=${() => setSelected(null)} />` : null}
  </div>`;
}

function diffRows(before, after) {
  const b = before || {}, a = after || {};
  const keys = [...new Set([...Object.keys(b), ...Object.keys(a)])].sort();
  const rows = [];
  for (const k of keys) {
    const hb = k in b, ha = k in a;
    const vb = JSON.stringify(b[k]), va = JSON.stringify(a[k]);
    let cls = "same";
    if (!hb && ha) cls = "add";
    else if (hb && !ha) cls = "del";
    else if (vb !== va) cls = "chg";
    rows.push({ k, cls, vb: hb ? vb : null, va: ha ? va : null });
  }
  return rows;
}

function AuditDrawer({ entry, onClose }) {
  const rows = (entry.before || entry.after) ? diffRows(entry.before, entry.after) : [];
  return html`<${Drawer} open=${true} width=${640} title=${entry.action} onClose=${onClose}>
    <div class="editor">
      <dl class="kv">
        <dt>${t("audit.dtWhen")}</dt><dd title=${entry.ts}>${fmtDateTime(entry.ts)}</dd>
        <dt>${t("audit.dtActor")}</dt><dd><span class="badge plain">${entry.actor_kind}</span> ${entry.actor_name || "—"}${entry.actor_id ? html` <span class="muted small">#${entry.actor_id}</span>` : null}</dd>
        <dt>${t("audit.dtResource")}</dt><dd>${entry.resource_kind || "—"} ${entry.resource_id ? html`<span class="mono">${entry.resource_id}</span>` : ""}</dd>
        ${entry.trace_id ? html`<dt>${t("audit.dtTrace")}</dt><dd class="mono small">${entry.trace_id}</dd>` : null}
      </dl>

      ${rows.length === 0 ? html`<p class="muted">${t("audit.noSnapshot")}</p>`
        : html`<h3 class="why-h">${t("audit.changesHeading")}</h3>
          <table class="tbl diff"><thead><tr><th>${t("audit.colField")}</th><th>${t("audit.colBefore")}</th><th>${t("audit.colAfter")}</th></tr></thead>
            <tbody>${rows.filter((r) => r.cls !== "same").map((r) => html`<tr key=${r.k} class=${"diff-" + r.cls}>
              <td class="mono small">${r.k}</td>
              <td class="mono small">${r.vb ?? "—"}</td>
              <td class="mono small">${r.va ?? "—"}</td>
            </tr>`)}</tbody></table>
          ${rows.every((r) => r.cls === "same") ? html`<p class="muted small">${t("audit.noFieldChanged")}</p>` : null}`}
    </div>
  </${Drawer}>`;
}
