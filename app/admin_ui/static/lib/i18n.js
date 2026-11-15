// Minimal i18n runtime for the build-less admin UI.
//
// English is the source catalog; any other language falls back to it per-key,
// and an unknown key falls back to itself so a gap is visible in dev. Catalogs
// are plain ESM modules, so there is no runtime fetch and nothing for the
// strict CSP to block. The current language lives in a module variable read by
// t() at render time; the app re-renders on change (a root state) so switching
// is live. Persisted in localStorage("alertd.lang"); first visit guesses from
// the browser, else English.
import en from "../i18n/en.js";
import ro from "../i18n/ro.js";

const CATALOGS = { en, ro };

export const LANGS = [
  { id: "en", label: "English" },
  { id: "ro", label: "Română" },
];
const LANG_IDS = new Set(LANGS.map((l) => l.id));

function detect() {
  try {
    const stored = localStorage.getItem("alertd.lang");
    if (LANG_IDS.has(stored)) return stored;
  } catch { /* private mode */ }
  try {
    const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
    if (LANG_IDS.has(nav)) return nav;
  } catch { /* no navigator */ }
  return "en";
}

let _lang = detect();

export function getLang() { return _lang; }

/** Text that comes as a string or as {en, ro, …} (e.g. a pack's name):
 *  the current language, else English, else the first one given. */
export function lt(value) {
  if (value == null) return "";
  if (typeof value !== "object") return String(value);
  return value[_lang] ?? value.en ?? Object.values(value)[0] ?? "";
}

export function setLang(lang) {
  _lang = LANG_IDS.has(lang) ? lang : "en";
  try { localStorage.setItem("alertd.lang", _lang); } catch { /* private mode */ }
  try { document.documentElement.lang = _lang; } catch { /* no document */ }
  return _lang;
}

// Resolve a key to any catalog NODE (object, array, or string), or undefined.
function resolve(catalog, key) {
  let node = catalog;
  for (const part of key.split(".")) {
    if (node && typeof node === "object" && part in node) node = node[part];
    else return undefined;
  }
  return node;
}

function lookup(catalog, key) {
  const node = resolve(catalog, key);
  return typeof node === "string" ? node : undefined;
}

// Translate a whole structured NODE (object/array/string), not just a leaf
// string — used for the per-kind help panels, whose content is a small tree
// of lead/purpose/fields/example. Falls back to the English node when the
// active language lacks the key, then to undefined. Pure: no I/O, no DOM.
export function tnode(key) {
  let node = resolve(CATALOGS[_lang], key);
  if (node === undefined && _lang !== "en") node = resolve(CATALOGS.en, key);
  return node;
}

// Translate `key`; fill {name} placeholders from `params`. Falls back to the
// English string, then to the key itself. Pure: no I/O, no DOM.
export function t(key, params) {
  let s = lookup(CATALOGS[_lang], key);
  if (s === undefined && _lang !== "en") s = lookup(CATALOGS.en, key);
  if (s === undefined) s = key;
  if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m));
  return s;
}
