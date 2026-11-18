// Rule expressions in the editor (rules review RL-28): the function catalog
// behind the cheat-sheet and completion, and ExprInput — a textarea that
// completes variable and function names. A Python test checks that the catalog
// lists every function the server knows (app/core/eval.py FUNCTION_NAMES).
import { html, useState, useRef, useEffect } from "./h.js";
import { useEscapeLayer } from "./dialog.js";
import { t } from "./i18n.js";

// [signature, i18n key of the description, function names]. Order = cheat-sheet.
export const EXPR_FUNCTIONS = [
  ['fresh("name", sec)', "rules.cheatFresh", ["fresh"]],
  ['has("name")', "rules.cheatHas", ["has"]],
  ['var_age("name")', "rules.cheatVarAge", ["var_age"]],
  ["coalesce(x, default)", "rules.cheatCoalesce", ["coalesce"]],
  ["between(x, lo, hi)", "rules.cheatBetween", ["between"]],
  ["any([…]) / all([…])", "rules.cheatAnyAll", ["any", "all"]],
  ["clamp(x, lo, hi)", "rules.cheatClamp", ["clamp"]],
  ["avg([a, b, …])", "rules.cheatAvg", ["avg"]],
  ["abs min max round sum", "rules.cheatNumeric", ["abs", "min", "max", "round", "sum"]],
  ["int(x) float(x) bool(x)", "rules.cheatConvert", ["int", "float", "bool"]],
  ["contains(s, sub)", "rules.cheatContains", ["contains"]],
  ["startswith(s, p) / endswith(s, p)", "rules.cheatStartsWith", ["startswith", "endswith"]],
  ["lower(s) upper(s) len(s)", "rules.cheatText", ["lower", "upper", "len"]],
  ["regex_match(s, pat)", "rules.cheatRegex", ["regex_match"]],
  ['in_window(start, end)', "rules.cheatInWindow", ["in_window"]],
  ["hour_now() dow_now() month_now()", "rules.cheatHourNow", ["hour_now", "dow_now", "month_now"]],
  ["is_weekend()", "rules.cheatWeekend", ["is_weekend"]],
  ["is_daylight() / sun_elevation()", "rules.cheatSun", ["is_daylight", "sun_elevation"]],
  ["now() / since_seconds(ts)", "rules.cheatNow", ["now", "since_seconds"]],
];

// Syntax rows of the cheat-sheet (no function names).
const EXPR_SYNTAX = [
  ["x in [a, b]", "rules.cheatIn"],
  ["a if cond else b", "rules.cheatTernary"],
  ["AND OR NOT", "rules.cheatBoolean"],
  ["true false null", "rules.cheatLiterals"],
];

/** Cheat-sheet rows [signature, description], translated at render time. */
export function cheatRows() {
  return [...EXPR_FUNCTIONS.map(([sig, key]) => [sig, t(key)]), ...EXPR_SYNTAX.map(([sig, key]) => [sig, t(key)])];
}

const FUNCTION_NAMES = EXPR_FUNCTIONS.flatMap(([, , names]) => names);
const MAX_ITEMS = 8;

/** Suggestions for the word that ends at ``caret``: variables (inserted as
 *  is) and functions (inserted with "("). Prefix matches first, then the
 *  names that contain the word; nothing under two characters or once the
 *  word is complete. Returns ``{ start, items: [{ label, insert, kind }] }``. */
export function completions(text, caret, variables = []) {
  const m = /[A-Za-z_][\w.]*$/.exec(text.slice(0, caret));
  if (!m || m[0].length < 2) return { start: caret, items: [] };
  const word = m[0].toLowerCase();
  const pool = [
    ...variables.map((v) => ({ label: v, insert: v, kind: "var" })),
    ...FUNCTION_NAMES.map((f) => ({ label: f + "()", insert: f + "(", kind: "fn" })),
  ];
  const name = (it) => it.insert.replace(/\($/, "").toLowerCase();
  if (pool.some((it) => name(it) === word && it.kind === "var")) return { start: m.index, items: [] };
  const starts = pool.filter((it) => name(it).startsWith(word) && name(it) !== word);
  const inside = pool.filter((it) => !name(it).startsWith(word) && name(it).includes(word));
  return { start: m.index, items: [...starts, ...inside].slice(0, MAX_ITEMS) };
}

let _seq = 0;

/** Expression textarea with completion. ``onChange(value)``; other props
 *  (aria-*, placeholder, rows) go to the textarea. */
export function ExprInput({ id, value, onChange, variables = [], ...rest }) {
  const ref = useRef(null);
  const [listId] = useState(() => `expr-sugg-${++_seq}`);
  const [sugg, setSugg] = useState({ start: 0, items: [] });
  const [active, setActive] = useState(0);
  const pendingCaret = useRef(null);
  const open = sugg.items.length > 0;
  const close = () => setSugg({ start: 0, items: [] });
  // Escape closes the list, not the editor drawer around it.
  useEscapeLayer(open, close);

  useEffect(() => {
    if (pendingCaret.current != null && ref.current) {
      ref.current.setSelectionRange(pendingCaret.current, pendingCaret.current);
      pendingCaret.current = null;
    }
  });

  function refresh(el) {
    const next = completions(el.value, el.selectionStart ?? el.value.length, variables);
    setSugg(next);
    setActive(0);
  }
  function accept(item) {
    const el = ref.current;
    const caret = el?.selectionStart ?? value.length;
    const text = el?.value ?? value;
    const next = text.slice(0, sugg.start) + item.insert + text.slice(caret);
    pendingCaret.current = sugg.start + item.insert.length;
    onChange(next);
    close();
    el?.focus();
  }
  function onKeyDown(e) {
    if (!open) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((active + 1) % sugg.items.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((active - 1 + sugg.items.length) % sugg.items.length); }
    else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); accept(sugg.items[active]); }
  }
  const optId = (i) => `${listId}-${i}`;
  return html`<div class="expr-input">
    <textarea id=${id} ref=${ref} class="mono" spellcheck="false" autocomplete="off" value=${value} ...${rest}
      aria-autocomplete="list" aria-controls=${open ? listId : undefined}
      aria-activedescendant=${open ? optId(active) : undefined}
      onInput=${(e) => { onChange(e.target.value); refresh(e.target); }}
      onKeyDown=${onKeyDown} onBlur=${close}></textarea>
    ${open ? html`<ul id=${listId} role="listbox" class="expr-suggest" aria-label=${t("rules.suggestions")}>
      ${sugg.items.map((it, i) => html`<li key=${it.kind + it.label} id=${optId(i)} role="option"
          aria-selected=${i === active ? "true" : "false"} class=${i === active ? "active" : ""}
          onMouseDown=${(e) => { e.preventDefault(); accept(it); }} onMouseMove=${() => setActive(i)}>
        <span class="mono">${it.label}</span>
        <span class="muted small">${it.kind === "fn" ? t("rules.suggestFunction") : t("rules.suggestVariable")}</span>
      </li>`)}
    </ul>` : null}
  </div>`;
}
