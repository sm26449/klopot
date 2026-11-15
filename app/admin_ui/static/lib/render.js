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

// ── Numbers exactly as the server formats them (app/core/rendering.py) ──
// Python rounds half to even on the exact binary value (round(2.5) == 2,
// f"{0.25:.1f}" == "0.2"), clamps digit counts to ±12, prints a float with
// "{:g}" (6 significant digits) and an integral one as a whole number. The
// shared cases in tests/js/support/render_parity.json keep the two equal.
const MAX_FILTER_DIGITS = 12;
const clampDigits = (n) => Math.max(-MAX_FILTER_DIGITS, Math.min(MAX_FILTER_DIGITS, n));
const PY_FLOAT = /^[+-]?(?:(?:\d(?:_?\d)*)(?:\.(?:\d(?:_?\d)*)?)?|\.\d(?:_?\d)*)(?:[eE][+-]?\d(?:_?\d)*)?$/;
const PY_SPECIAL = /^[+-]?(?:inf|infinity|nan)$/i;

/** Python's float(value): a number, a bool, or numeric text — else an error. */
function toFloat(value) {
  if (typeof value === "number") return value;
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value !== "string") throw new Error("not a number");
  const s = value.trim();
  if (PY_SPECIAL.test(s)) return s.toLowerCase().includes("nan") ? NaN : (s.startsWith("-") ? -Infinity : Infinity);
  if (!PY_FLOAT.test(s)) throw new Error("not a number");
  return Number(s.replace(/_/g, ""));
}

/** Digits of |x| rounded half to even at `d` decimals (d ≥ 0, |x| < 1e21):
 *  [integer part, fraction]. toFixed(100) is the exact expansion. */
function halfEven(x, d) {
  const [ip, fp] = Math.abs(x).toFixed(100).split(".");
  const rest = fp.slice(d);
  const last = Number((ip + fp.slice(0, d)).slice(-1));
  const up = rest[0] > "5" || (rest[0] === "5" && (/[1-9]/.test(rest.slice(1)) || last % 2 === 1));
  let digits = BigInt(ip + fp.slice(0, d)) + (up ? 1n : 0n);
  const str = digits.toString().padStart(d + 1, "0");
  return [str.slice(0, str.length - d), str.slice(str.length - d)];
}

function signOf(x) { return x < 0 || Object.is(x, -0) ? "-" : ""; }

/** Python f"{x:.{d}f}". */
function pyFixed(x, d) {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  if (Math.abs(x) >= 1e21) return BigInt(x).toString() + (d ? "." + "0".repeat(d) : "");
  const [ip, fp] = halfEven(x, d);
  return signOf(x) + ip + (d ? "." + fp : "");
}

/** Python round(x, d) for a float. */
function pyRound(x, d) {
  if (!Number.isFinite(x)) return x;
  if (d >= 0) return Math.abs(x) >= 1e21 ? x : Number(pyFixed(x, d));
  const m = 10 ** -d;
  const q = x / m;
  let n = Math.floor(q);
  const diff = q - n;
  if (diff > 0.5 || (diff === 0.5 && ((n + 0.5) * m !== x || n % 2 !== 0))) n += 1;
  return n * m || (x < 0 ? -0 : 0);
}

/** Python f"{x:g}" for a non-integral float. */
function pyG(x) {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  const exp = Number(x.toExponential(5).split("e")[1]);
  if (exp < -4 || exp >= 6) {
    const [mant, e] = x.toExponential(5).split("e");
    const m = mant.includes(".") ? mant.replace(/0+$/, "").replace(/\.$/, "") : mant;
    const n = Number(e);
    return `${m}e${n < 0 ? "-" : "+"}${String(Math.abs(n)).padStart(2, "0")}`;
  }
  const out = pyFixed(x, 5 - exp);
  return out.includes(".") ? out.replace(/0+$/, "").replace(/\.$/, "") : out;
}

/** How the server prints a value once the filters ran. */
function pyStr(value) {
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value !== "number") return String(value);
  if (Number.isFinite(value) && Number.isInteger(value)) return BigInt(value).toString();
  return pyG(value);
}

/** Python str(value) for the text filters (lower / upper / jsonstr). A JS
 *  number cannot tell 7 from 7.0, so numbers keep their shortest form. */
function pyText(value) {
  if (typeof value === "boolean") return value ? "True" : "False";
  return String(value);
}

function applyFilter(value, expr) {
  const m = expr.match(/^([a-zA-Z_]\w*)(?:\((.*)\))?$/);
  if (!m) throw new Error("bad filter");
  const f = m[1], arg = m[2];
  const digits = (fallback) => {
    if (!arg) return fallback;
    if (!/^\s*[+-]?\d+\s*$/.test(arg)) throw new Error("bad digits");
    return clampDigits(parseInt(arg, 10));
  };
  switch (f) {
    case "round": return pyRound(toFloat(value), digits(0));
    case "fixed": return pyFixed(toFloat(value), Math.max(0, digits(1)));
    case "pct": {
      const r = pyRound(toFloat(value), 0);
      if (!Number.isFinite(r)) throw new Error("not finite");
      return BigInt(r).toString();
    }
    case "div": {
      if (!arg) throw new Error("div requires an argument");
      const by = toFloat(arg);
      if (by === 0) throw new Error("division by zero");
      return toFloat(value) / by;
    }
    case "lower": return pyText(value).toLowerCase();
    case "upper": return pyText(value).toUpperCase();
    case "json": return JSON.stringify(value);
    case "jsonstr": return JSON.stringify(pyText(value)).slice(1, -1);
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
  return pyStr(value);
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
