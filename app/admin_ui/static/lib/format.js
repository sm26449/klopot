// Formatting helpers shared by views. Dates and relative times follow the
// active UI locale via Intl, not a hard-coded English form (audit UX-017).
import { getLang } from "./i18n.js";

// `tz` (an IANA zone like "UTC" or "Europe/Bucharest") renders the instant in
// that zone instead of the browser's — used by the cron preview so the time and
// its "(tz)" label always agree, across any offset and DST (audit UX-010/R3).
// An unknown zone falls back to the browser zone rather than throwing.
export function fmtDateTime(iso, { tz } = {}) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  const opts = {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  };
  if (tz) {
    try { return d.toLocaleString(getLang(), { ...opts, timeZone: tz }); }
    catch { /* invalid IANA zone — fall through to the browser zone */ }
  }
  return d.toLocaleString(getLang(), opts);
}

export function fmtRelative(iso) {
  if (!iso) return "—";
  const ms = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(ms);
  const units = [["day", 86400000], ["hour", 3600000], ["minute", 60000], ["second", 1000]];
  // "short", not "narrow": CLDR's narrow Romanian is "-9 m" / "+3 h", which
  // reads like arithmetic; short gives "acum 9 min." / "9 min. ago".
  const rtf = new Intl.RelativeTimeFormat(getLang(), { numeric: "auto", style: "short" });
  for (const [u, size] of units) {
    if (abs >= size || u === "second") return rtf.format(Math.round(ms / size), u);
  }
  return rtf.format(0, "second");
}

export function fmtSeconds(sec) {
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60), s = sec % 60;
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}
