// Icon field for templates: free entry (any emoji) with a live preview, plus a
// searchable palette from lib/icons.js. The palette registers on the dialog
// stack (useDialog) so Escape closes it — not the editor Drawer around it —
// and focus returns to the button that opened it.
import { html, useState, useRef } from "./h.js";
import { useDialog } from "./dialog.js";
import { ICON_GROUPS, isValidIcon, searchIcons } from "./icons.js";
import { t } from "./i18n.js";

function IconPalette({ id, value, onPick, onClose }) {
  const [query, setQuery] = useState("");
  const ref = useRef(null);
  useDialog(true, onClose, ref);
  const results = searchIcons(query);
  const groups = ICON_GROUPS
    .map((g) => [g.id, results.filter((r) => r.group === g.id)])
    .filter(([, items]) => items.length);
  return html`<div class="icon-panel" id=${id} ref=${ref} role="dialog" aria-label=${t("icons.panelAria")}>
    <input type="search" aria-label=${t("icons.search")} placeholder=${t("icons.search")}
      value=${query} onInput=${(e) => setQuery(e.target.value)} />
    ${groups.length === 0 ? html`<p class="muted small">${t("icons.none")}</p>`
      : groups.map(([g, items]) => html`<div key=${g} class="icon-group">
          <div class="icon-group-title">${t(`icons.group.${g}`)}</div>
          <div class="icon-grid">${items.map((i) => html`<button type="button" key=${i.emoji}
            class=${"icon-cell" + (i.emoji === value ? " selected" : "")} title=${i.name}
            aria-label=${i.name} aria-pressed=${i.emoji === value}
            onClick=${() => onPick(i.emoji)}>${i.emoji}</button>`)}</div>
        </div>`)}
  </div>`;
}

export function IconPicker({ id, value, onChange }) {
  const [open, setOpen] = useState(false);
  const current = value || "";
  const valid = isValidIcon(current);
  const panelId = `${id}-palette`;
  return html`<div class="icon-picker">
    <div class="icon-input">
      <span class="icon-preview" aria-hidden="true">${valid && current.trim() ? current : "·"}</span>
      <input id=${id} value=${current} maxlength="8" placeholder="⚠️" autocomplete="off"
        aria-invalid=${valid ? "false" : "true"} aria-describedby=${valid ? undefined : `${id}-error`}
        onInput=${(e) => onChange(e.target.value)} />
      <button type="button" class="btn sm" aria-expanded=${open} aria-controls=${panelId}
        onClick=${() => setOpen(!open)}>${t("icons.choose")}</button>
      ${current ? html`<button type="button" class="btn sm" aria-label=${t("icons.clear")} title=${t("icons.clear")}
        onClick=${() => onChange("")}>✕</button>` : null}
    </div>
    ${valid ? null : html`<div class="error" id=${`${id}-error`}>${t("icons.invalid")}</div>`}
    ${open ? html`<${IconPalette} id=${panelId} value=${current}
      onPick=${(emoji) => { onChange(emoji); setOpen(false); }} onClose=${() => setOpen(false)} />` : null}
  </div>`;
}
