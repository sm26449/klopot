// Secondary lookups — picker options, autocomplete, a count shown beside a
// form. When one fails the page keeps working, but an empty list must not
// pass for "there is nothing" (Copilot hygiene #8): the operator gets one
// toast (at most every few seconds, however many lookups failed together)
// and the error goes to the console.
import { toast } from "./toast.js";
import { t } from "./i18n.js";

const QUIET_MS = 5000;
let lastToast = 0;

export function lookupFailed(err) {
  console.error("lookup failed", err);
  const now = Date.now();
  if (now - lastToast < QUIET_MS) return;
  lastToast = now;
  toast.error(t("common.lookupFailed"));
}

/** `promise`, or `fallback` after telling the operator it failed. */
export function lookup(promise, fallback) {
  return promise.catch((err) => { lookupFailed(err); return fallback; });
}
