// Global search (Ctrl+K / ⌘K): jump to any page or configured item.
//
// A dialog with a combobox: type to filter, ↑/↓ to move, Enter to open,
// Escape to close (through the dialog stack, lib/dialog.js). Pages come from
// the shell's NAV; items (templates, rules, variables, channels, inputs,
// packs) are loaded when the palette opens, so it is always current.
import { html, useEffect, useRef, useState, useMemo } from "./h.js";
import { api } from "./api.js";
import { useDialog } from "./dialog.js";
import { navigate } from "./router.js";
import { t, lt } from "./i18n.js";

const MAX_RESULTS = 30;

/** Score `text` against `query`: substring beats in-order letters; 0 = no match. */
export function matchScore(text, query) {
  const s = String(text).toLowerCase(), q = query.trim().toLowerCase();
  if (!q) return 1;
  const at = s.indexOf(q);
  if (at >= 0) return 1000 - at * 2 - (s.length - q.length) * 0.1;
  let i = 0;
  for (const ch of s) if (ch === q[i]) i++;
  return i === q.length ? 100 - (s.length - q.length) * 0.1 : 0;
}

async function loadItems() {
  const safe = (p) => p.catch(() => ({ items: [] }));
  const [tpl, rules, vars, chans, inputs, packs] = await Promise.all([
    safe(api.get("/v1/templates", { limit: 500 })), safe(api.get("/v1/rules", { limit: 500 })),
    safe(api.get("/v1/variables", { limit: 500 })), safe(api.get("/v1/channels", { limit: 500 })),
    safe(api.get("/v1/inputs", { limit: 500 })), safe(api.get("/v1/packs")),
  ]);
  return [
    ...tpl.items.map((x) => ({ kind: "template", label: x.type, hint: x.title_template, go: () => navigate("/templates", { search: x.type }) })),
    ...rules.items.map((x) => ({ kind: "rule", label: x.name, hint: x.condition_expr, go: () => navigate(`/rules/${x.id}`) })),
    ...vars.items.map((x) => ({ kind: "variable", label: x.name, hint: x.source, go: () => navigate("/variables", { search: x.name }) })),
    ...chans.items.map((x) => ({ kind: "channel", label: x.name, hint: x.kind, go: () => navigate("/channels") })),
    ...inputs.items.map((x) => ({ kind: "input", label: x.name, hint: x.kind, go: () => navigate("/inputs") })),
    ...packs.items.map((x) => ({ kind: "pack", label: lt(x.name), hint: lt(x.description), go: () => navigate("/packs") })),
  ];
}

export function CommandPalette({ open, onClose, pages }) {
  const ref = useRef(null);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState(null);
  const [active, setActive] = useState(0);
  useDialog(open, onClose, ref);

  useEffect(() => {
    if (!open) return;
    setQuery(""); setActive(0); setItems(null);
    loadItems().then(setItems);
  }, [open]);

  const results = useMemo(() => {
    const all = [...pages.map((p) => ({ kind: "page", label: p.label, go: () => navigate(p.path) })), ...(items || [])];
    return all.map((r) => ({ ...r, score: Math.max(matchScore(r.label, query), matchScore(r.hint || "", query) * 0.5) }))
      .filter((r) => r.score > 0).sort((a, b) => b.score - a.score).slice(0, MAX_RESULTS);
  }, [pages, items, query]);
  useEffect(() => { setActive(0); }, [query]);

  if (!open) return null;
  const choose = (r) => { onClose(); r.go(); };
  function onKey(e) {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(results.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter" && results[active]) { e.preventDefault(); choose(results[active]); }
  }
  const optId = (i) => `cmdk-opt-${i}`;
  return html`<div class="modal-overlay palette-overlay" onClick=${onClose}>
    <div ref=${ref} class="modal palette" role="dialog" aria-modal="true" aria-label=${t("palette.title")}
         tabindex="-1" onClick=${(e) => e.stopPropagation()}>
      <input class="palette-input" type="text" role="combobox" aria-expanded="true" aria-controls="cmdk-list"
        aria-autocomplete="list" aria-activedescendant=${results.length ? optId(active) : undefined}
        aria-label=${t("palette.title")} placeholder=${t("palette.placeholder")}
        value=${query} onInput=${(e) => setQuery(e.target.value)} onKeyDown=${onKey} />
      <ul id="cmdk-list" role="listbox" class="palette-list" aria-label=${t("palette.results")}>
        ${results.map((r, i) => html`<li key=${r.kind + ":" + r.label} id=${optId(i)} role="option" aria-selected=${i === active ? "true" : "false"}
            class=${i === active ? "active" : ""} onMouseMove=${() => setActive(i)} onClick=${() => choose(r)}>
          <span class="palette-kind">${t(`palette.kind.${r.kind}`)}</span>
          <span class="palette-label">${r.label}</span>
          ${r.hint ? html`<span class="palette-hint muted small">${r.hint}</span>` : null}
        </li>`)}
      </ul>
      ${!results.length ? html`<p class="muted small palette-empty" role="status">${items === null ? t("common.loading") : t("palette.none")}</p>` : null}
      <p class="palette-keys muted small" aria-hidden="true">${t("palette.keys")}</p>
    </div>
  </div>`;
}
