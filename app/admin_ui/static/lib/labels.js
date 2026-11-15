// Display names for enum values and codes the API returns (severity, health
// status, suppression reason, health component and detail code). Unknown
// values fall back to the raw value, so a newer server never shows a key.
import { t } from "./i18n.js";

function label(group, value) {
  if (value === null || value === undefined || value === "") return "";
  const key = `labels.${group}.${value}`;
  const text = t(key);
  return text === key ? String(value) : text;
}

export const sevLabel = (s) => label("severity", s);
export const statusLabel = (s) => label("status", s);
export const reasonLabel = (r) => label("reason", r);
export const componentLabel = (c) => label("component", c);

/** A health component's detail in the UI language (falls back to `detail`). */
export function healthDetail(comp) {
  if (!comp) return "";
  const key = comp.code ? `labels.healthDetail.${comp.code}` : null;
  const params = { ...(comp.params || {}) };
  for (const [k, v] of Object.entries(params)) if (Array.isArray(v)) params[k] = v.join(", ");
  let text = key && t(key, params) !== key ? t(key, params) : comp.detail || "";
  if (comp.params?.optional_down?.length) text += ` · ${t("labels.healthDetail.optionalDown", { names: params.optional_down })}`;
  return text;
}
