// Unit tests for the i18n runtime: nested lookup, source default, missing-key
// and per-key fallback, interpolation, language switch + clamp, and a
// completeness guard that every source key resolves in every shipped language.
import { test } from "node:test";
import assert from "node:assert/strict";
import { t, getLang, setLang, LANGS } from "../../app/admin_ui/static/lib/i18n.js";
import en from "../../app/admin_ui/static/i18n/en.js";

test("defaults to English and looks up nested keys", () => {
  assert.equal(getLang(), "en");
  assert.equal(t("nav.channels"), "Channels");
  assert.equal(t("navGroup.system"), "System");
  assert.equal(t("shell.notFoundTitle"), "Not found");
});

test("unknown key falls back to the key itself", () => {
  assert.equal(t("no.such.key"), "no.such.key");
});

test("interpolates {placeholders}", () => {
  // No shipped string needs params yet; the missing-key path returns the key,
  // which exercises the same replace().
  assert.equal(t("Hi {name}", { name: "Ada" }), "Hi Ada");
  assert.equal(t("Hi {name}", {}), "Hi {name}"); // unknown param left intact
});

test("switches language and clamps unknown codes to English", () => {
  try {
    assert.equal(setLang("ro"), "ro");
    assert.equal(t("nav.channels"), "Canale");
    assert.equal(t("common.signOut"), "Deconectare");
    assert.equal(setLang("zz"), "en"); // unknown → English
    assert.equal(t("nav.channels"), "Channels");
  } finally {
    setLang("en");
  }
});

function flatten(obj, prefix = "") {
  const out = [];
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object") out.push(...flatten(v, key));
    else out.push(key);
  }
  return out;
}

test("every source key resolves in every language (fallback covers gaps)", () => {
  const keys = flatten(en);
  try {
    for (const lang of LANGS.map((l) => l.id)) {
      setLang(lang);
      for (const key of keys) {
        assert.notEqual(t(key), key, `${lang}: "${key}" returned the raw key`);
      }
    }
  } finally {
    setLang("en");
  }
});
