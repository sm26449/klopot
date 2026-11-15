// Client-side template preview — mirrors app/core/rendering.py closely
// enough for a live editor preview of UNSAVED title/message edits (the
// server's POST /preview only renders the already-stored template).
//
// Supports {name} and %name% placeholders, dotted lookups, and the same
// pipe filters as the server (round, fixed, div, pct, lower, upper, json,
// jsonstr — tests/core/test_rendering.py keeps the two lists equal).
// Unresolved names render as [?name] and are collected as missingVars.

const BRACE = /\{([^{}]+?)\}/g;
const PERCENT = /%([a-zA-Z_][\w.]*(?:\s*\|\s*[a-zA-Z_]\w*(?:\([^)]*\))?)*)%/g;
// Both syntaxes in ONE pattern, substituted in one pass like the server's
// _PLACEHOLDER: a value containing %x% or {x} is placed literally, never
// expanded again (review K21).
const PLACEHOLDER = new RegExp(`${BRACE.source}|${PERCENT.source}`, "g");
const MAX_RENDER_LEN = 100000;   // the server's _MAX_RENDER_LEN

// Own keys only: "constructor" or "toString" is not a value of the context.
const own = (obj, key) => obj !== null && typeof obj === "object" && Object.hasOwn(obj, key);

function lookup(name, ctx) {
  if (own(ctx, name)) return ctx[name];
  const parts = name.split(".");
  if (parts.length === 1) return undefined;
  let obj = ctx;
  for (const p of parts) {
    if (own(obj, p)) obj = obj[p];
    else return undefined;
  }
  return obj;
}

function applyFilter(value, expr) {
  const m = expr.match(/^([a-zA-Z_]\w*)(?:\((.*)\))?$/);
  if (!m) throw new Error("bad filter");
  const f = m[1], arg = m[2];
  const num = Number(value);
  switch (f) {
    case "round": return Number(num.toFixed(arg ? parseInt(arg, 10) : 0));
    case "fixed": return num.toFixed(arg ? parseInt(arg, 10) : 1);
    case "pct": return String(Math.round(num));
    case "div": return num / Number(arg);
    case "lower": return String(value).toLowerCase();
    case "upper": return String(value).toUpperCase();
    case "json": return JSON.stringify(value);
    case "jsonstr": return JSON.stringify(String(value)).slice(1, -1);
    default: throw new Error("unknown filter " + f);
  }
}

function resolve(spec, ctx, missing) {
  const parts = spec.split("|").map((s) => s.trim());
  const name = parts[0];
  let value = lookup(name, ctx);
  if (value === undefined || value === null) { missing.add(name); return `[?${name}]`; }
  for (const f of parts.slice(1)) {
    try { value = applyFilter(value, f); } catch { return `[?${name}|${f}]`; }
  }
  if (typeof value === "number" && Number.isInteger(value)) return String(value);
  return String(value);
}

/** The placeholder names a template uses ({disk.used_pct | fixed(1)} → "disk.used_pct"). */
export function placeholderNames(...templates) {
  const names = new Set();
  for (const tpl of templates) {
    if (!tpl) continue;
    for (const re of [BRACE, PERCENT]) {
      for (const m of tpl.matchAll(new RegExp(re.source, "g"))) names.add(m[1].split("|")[0].trim());
    }
  }
  return [...names].filter(Boolean);
}

// A plausible stand-in for a placeholder with no live value, so the preview
// reads like a real alert: numbers for names that look numeric, ‹name› else.
function sampleFor(name) {
  const n = name.toLowerCase();
  if (/(pct|percent|ratio|level|usage|load|soc)/.test(n)) return 87;
  if (/temp/.test(n)) return 41.5;
  if (/(count|total|num|errors|dispatched|suppressed)$|_n$/.test(n)) return 3;
  if (/(latency|ms|sec|seconds|age)/.test(n)) return 120;
  return `‹${name}›`;
}

/** A preview context for `names`: live values first, samples for the rest.
 *  Dotted names become nested objects ({"disk": {"used_pct": 87}}). */
// Path segments that would reach Object.prototype through a plain object.
const UNSAFE_KEYS = new Set(["__proto__", "constructor", "prototype"]);

export function sampleContext(names, live = {}) {
  const ctx = {};
  for (const name of names) {
    const parts = name.split(".");
    // A placeholder name is template text: never let it walk to a prototype (K21).
    if (parts.some((p) => UNSAFE_KEYS.has(p))) continue;
    const value = own(live, name) ? live[name] : sampleFor(name);
    let obj = ctx;
    for (const p of parts.slice(0, -1)) obj = (obj[p] = own(obj, p) && typeof obj[p] === "object" && obj[p] ? obj[p] : {});
    obj[parts[parts.length - 1]] = value;
  }
  return ctx;
}

// Returns { text, missing: [names] }.
export function renderTemplate(template, ctx) {
  const missing = new Set();
  if (!template) return { text: "", missing: [] };
  const out = template.replace(PLACEHOLDER, (_, brace, percent) => resolve((brace ?? percent).trim(), ctx, missing));
  return { text: out.length > MAX_RENDER_LEN ? out.slice(0, MAX_RENDER_LEN) : out, missing: [...missing] };
}
