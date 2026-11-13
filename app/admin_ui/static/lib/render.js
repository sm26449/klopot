// Client-side template preview — mirrors app/core/rendering.py closely
// enough for a live editor preview of UNSAVED title/message edits (the
// server's POST /preview only renders the already-stored template).
//
// Supports {name} and %name% placeholders, dotted lookups, and the
// common pipe filters (round, kw, pct, fixed, lower, upper). Unresolved
// names render as [?name] and are collected as missingVars.

const BRACE = /\{([^{}]+?)\}/g;
const PERCENT = /%([a-zA-Z_][\w.]*(?:\s*\|\s*[a-zA-Z_]\w*(?:\([^)]*\))?)*)%/g;

function lookup(name, ctx) {
  if (name in ctx) return ctx[name];
  const parts = name.split(".");
  if (parts.length === 1) return undefined;
  let obj = ctx;
  for (const p of parts) {
    if (obj && typeof obj === "object" && p in obj) obj = obj[p];
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
    case "kw": return (num / 1000).toFixed(1);
    case "pct": return String(Math.round(num));
    case "div": return num / Number(arg);
    case "lower": return String(value).toLowerCase();
    case "upper": return String(value).toUpperCase();
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

// Returns { text, missing: [names] }.
export function renderTemplate(template, ctx) {
  const missing = new Set();
  if (!template) return { text: "", missing: [] };
  let out = template.replace(BRACE, (_, g) => resolve(g.trim(), ctx, missing));
  out = out.replace(PERCENT, (_, g) => resolve(g.trim(), ctx, missing));
  return { text: out, missing: [...missing] };
}
