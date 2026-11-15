// Every page, desktop, in English and Romanian: renders without errors, no
// failed requests, no leaked i18n keys or junk values, no axe violations.
import { describe, test, before, after } from "node:test";
import assert from "node:assert/strict";
import { launch, session, go, watch, axe, ROUTES } from "./support.mjs";
import en from "../../app/admin_ui/static/i18n/en.js";

// Every key of the English catalog, flattened ("nav.rules", …). A key that shows
// up verbatim on a page is a missing translation call or a typo in t("…").
const KEYS = (() => {
  const out = new Set();
  const walk = (o, p) => { for (const [k, v] of Object.entries(o)) typeof v === "object" ? walk(v, `${p}${k}.`) : out.add(`${p}${k}`); };
  walk(en, "");
  return out;
})();
// Words that must not appear on a Romanian page (untranslated UI chrome).
const EN_IN_RO = /\b(Critical|Warning|Degraded|Real \+ test|unknown|no inputs declared|Unacknowledged|running|no overdue deliveries)\b|-\d+ m\b/;

async function inspect(page) {
  const info = await page.evaluate(() => {
    const text = (document.querySelector("main") || document.body).innerText;
    const junk = [...new Set(text.match(/\b(undefined|NaN|\[object Object\])\b/g) || [])];
    return { text, junk, h1: document.querySelectorAll("h1").length };
  });
  info.keys = [...new Set(info.text.match(/\b[a-z][a-zA-Z]*(\.[a-zA-Z]+)+\b/g) || [])].filter((k) => KEYS.has(k));
  return info;
}

for (const lang of ["en", "ro"]) describe(lang, () => {
  let browser, page;
  before(async () => { browser = await launch(); page = await session(browser, { lang }); });
  after(async () => { await browser?.close(); });

  for (const route of ROUTES) {
    test(`${lang} · ${route}`, async () => {
      const seen = watch(page);
      await go(page, route);
      const info = await inspect(page);
      page.removeAllListeners("console"); page.removeAllListeners("pageerror"); page.removeAllListeners("response");
      assert.deepEqual(seen.errors, [], "console / page errors");
      assert.deepEqual(seen.failed, [], "failed requests");
      assert.equal(info.h1, 1, "exactly one h1");
      assert.deepEqual(info.keys, [], "leaked i18n keys");
      assert.deepEqual(info.junk, [], "undefined / NaN / [object Object] on the page");
      if (lang === "ro") assert.doesNotMatch(info.text, EN_IN_RO, "untranslated English on a Romanian page");
      assert.deepEqual(await axe(page), [], "axe violations");
    });
  }
});

test("login page is a landmark with a heading and passes axe", async () => {
  const browser = await launch();
  try {
    const page = await (await browser.newContext()).newPage();
    await page.goto(`${process.env.E2E_URL}/admin/`, { waitUntil: "networkidle" });
    assert.equal(await page.locator("main").count(), 1, "login page has <main>");
    assert.equal(await page.locator("h1").count(), 1, "login page has one <h1>");
    assert.deepEqual(await axe(page), []);
  } finally {
    await browser.close();
  }
});
