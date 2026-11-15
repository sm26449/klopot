// Every page on a phone (Pixel 7: touch, 412×915): the menu button is reachable,
// the page title is not hidden under the sticky top bar, nothing overflows
// sideways and interactive targets are at least 44 px (WCAG 2.5.5 / platform HIG).
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { launch, session, go, ROUTES } from "./support.mjs";

const MIN_TARGET = 44;
let browser, page;
before(async () => { browser = await launch(); page = await session(browser, { lang: "ro", phone: true }); });
after(async () => { await browser?.close(); });

for (const route of ROUTES) {
  test(`phone · ${route}`, async () => {
    await go(page, route);
    const m = await page.evaluate((min) => {
      const vw = window.innerWidth, vh = window.innerHeight;
      const r = (el) => el && el.getBoundingClientRect();
      const toggle = r(document.querySelector(".nav-toggle"));
      // The sticky chrome: whichever of the brand bar / top bar is pinned.
      const pinned = [...document.querySelectorAll(".sidebar, .topbar")]
        .filter((e) => ["sticky", "fixed"].includes(getComputedStyle(e).position) && e.getBoundingClientRect().height > 0);
      const bar = pinned.length ? { height: Math.max(...pinned.map((e) => e.getBoundingClientRect().height)),
        bottom: Math.max(...pinned.map((e) => e.getBoundingClientRect().bottom)) } : null;
      const h1 = r(document.querySelector("main h1"));
      const visible = (el) => { const b = el.getBoundingClientRect(); return b.width > 0 && b.height > 0 && getComputedStyle(el).visibility !== "hidden"; };
      // Links inside running text are exempt (WCAG 2.5.8 "inline" exception).
      const inline = (e) => e.tagName === "A" && getComputedStyle(e).display === "inline";
      const small = [...document.querySelectorAll("main button, main a[href], main select, main input:not([type=checkbox]):not([type=radio]), main summary")]
        .filter(visible).filter((e) => !inline(e)).filter((e) => { const b = e.getBoundingClientRect(); return b.height < min - 0.5; })
        .slice(0, 6).map((e) => `${e.tagName.toLowerCase()}.${[...e.classList].join(".")} "${(e.innerText || e.getAttribute("aria-label") || "").trim().slice(0, 20)}" ${Math.round(e.getBoundingClientRect().height)}px`);
      // Wider than the screen is fine inside a horizontally scrollable box.
      const inScroller = (e) => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
        if (["auto", "scroll"].includes(getComputedStyle(p).overflowX) && p.getBoundingClientRect().right <= vw + 1) return true; } return false; };
      const wide = [...document.querySelectorAll("main *")]
        .filter((e) => visible(e) && e.getBoundingClientRect().right > vw + 1 && !inScroller(e))
        .slice(0, 4).map((e) => `${e.tagName.toLowerCase()}.${[...e.classList].join(".")}`);
      return {
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        toggleOnScreen: !!toggle && toggle.top >= 0 && toggle.bottom <= vh && toggle.left >= 0 && toggle.right <= vw,
        barHeight: bar ? Math.round(bar.height) : 0,
        h1Covered: !!(h1 && bar && h1.top < bar.bottom - 1),
        small, wide,
      };
    }, MIN_TARGET);
    assert.ok(m.toggleOnScreen, "menu button is on screen");
    assert.ok(m.barHeight <= 72, `sticky top bar is compact (${m.barHeight}px)`);
    assert.equal(m.h1Covered, false, "page title is not under the top bar");
    assert.ok(m.overflow <= 0, `no horizontal page scroll (${m.overflow}px)`);
    assert.deepEqual(m.wide, [], "elements wider than the screen");
    assert.deepEqual(m.small, [], `targets smaller than ${MIN_TARGET}px`);
  });
}

test("phone · the menu opens and navigates", async () => {
  await go(page, "templates");
  await page.click(".nav-toggle");
  const link = page.locator("nav.nav a[href='#/rules']");
  await link.waitFor({ state: "visible" });
  await link.click();
  await page.waitForFunction(() => location.hash === "#/rules");
  assert.equal(await page.locator("nav.nav a[href='#/rules']").isVisible(), false, "menu closes after navigating");
});

test("phone · language, theme and sign-out are in the menu", async () => {
  await go(page, "dashboard");
  assert.equal(await page.locator(".topbar").isVisible(), false, "no desktop top bar");
  await page.click(".nav-toggle");
  const prefs = page.locator("nav.nav .prefs-menu");
  await prefs.waitFor({ state: "visible" });
  assert.equal(await prefs.locator("select").count(), 3);
  assert.ok(await prefs.getByRole("button").last().isVisible(), "sign-out reachable");
  await page.click(".nav-toggle");
});

test("phone shows health and search once (brand bar), not the desktop copies", async () => {
  await go(page, "dashboard");
  const visible = async (sel) => page.locator(sel).evaluateAll((els) => els.filter((e) => e.getClientRects().length && getComputedStyle(e).display !== "none").length);
  assert.equal(await visible(".brand .brand-health"), 1);
  assert.equal(await visible(".brand .search-phone"), 1);
  assert.equal(await visible(".topbar"), 0, "desktop top bar hidden");
});


test("phone · Activity: the tabs stay on one row, the checkbox sits by its label", async () => {
  await go(page, "activity");
  const m = await page.evaluate(() => {
    const tops = [...document.querySelectorAll(".tabs .tab")].map((e) => Math.round(e.getBoundingClientRect().top));
    const box = document.querySelector(".filters .chk input").getBoundingClientRect();
    const label = document.querySelector(".filters .chk").getBoundingClientRect();
    return { rows: new Set(tops).size, gap: label.right - box.right, boxW: box.width, labelH: label.height };
  });
  assert.equal(m.rows, 1, "tabs on one row (they scroll sideways)");
  assert.ok(m.boxW < 30, `checkbox keeps its size (${m.boxW}px)`);
  assert.ok(m.labelH < 60, `label on one line (${m.labelH}px)`);
});

test("phone · dashboard: Refresh sits beside the title, not on a row of its own", async () => {
  await go(page, "dashboard");
  const m = await page.evaluate(() => ({
    h1: document.querySelector("main h1").getBoundingClientRect(),
    btn: document.querySelector(".page-head .actions .btn").getBoundingClientRect(),
  }));
  assert.ok(m.btn.top < m.h1.bottom, "button starts beside the heading");
});

test("phone · a list table is one card per row, each cell labelled by its column", async () => {
  await go(page, "log");
  const m = await page.evaluate(() => {
    const vw = window.innerWidth;
    const table = document.querySelector("main table.tbl");
    const row = table.querySelector("tbody tr");
    const cells = [...row.children];
    return {
      stacked: table.classList.contains("stacked"),
      rowDisplay: getComputedStyle(row).display,
      headerShown: table.querySelector("thead").getBoundingClientRect().height > 2,
      labels: cells.map((c) => getComputedStyle(c, "::before").content).filter((c) => c && c !== "none"),
      past: cells.filter((c) => c.getBoundingClientRect().right > vw + 1).length,
      role: table.getAttribute("role"),
    };
  });
  assert.ok(m.stacked, "the log table is stacked");
  assert.equal(m.rowDisplay, "block", "a row is a card");
  assert.equal(m.headerShown, false, "the header row is visually hidden");
  assert.ok(m.labels.length >= 3, `cells show their column names (${m.labels.join(", ")})`);
  assert.equal(m.past, 0, "no cell runs past the screen");
  assert.equal(m.role, "table", "table semantics kept for screen readers");
});
