// Shared helpers for the browser end-to-end tests (run by scripts/e2e.sh).
import { chromium, devices } from "playwright";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const BASE = process.env.E2E_URL;
export const PASSWORD = process.env.E2E_PASSWORD;
export const BOOTSTRAP_PASSWORD = process.env.E2E_BOOTSTRAP_PASSWORD;
export const ADMIN_KEY = process.env.E2E_ADMIN_KEY;
if (!BASE) throw new Error("E2E_URL is not set — run the e2e tests through scripts/e2e.sh");

export const ROUTES = ["setup", "dashboard", "log", "incidents", "snooze", "templates", "channels", "rules",
  "variables", "inputs", "schedules", "packs", "operations", "state", "api-keys", "api", "activity", "audit", "config", "account"];

const AXE = readFileSync(fileURLToPath(new URL("../../node_modules/axe-core/axe.min.js", import.meta.url)), "utf8");

export async function launch() {
  return chromium.launch();
}

/** A logged-in page. `phone: true` emulates a Pixel 7 (touch, coarse pointer). */
export async function session(browser, { lang = "en", phone = false, theme = "light" } = {}) {
  const ctx = await browser.newContext(phone ? { ...devices["Pixel 7"] } : { viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(([l, th]) => {
    try { localStorage.setItem("alertd.lang", l); localStorage.setItem("alertd.theme", th); localStorage.setItem("alertd.family", "klopot"); } catch { /* */ }
    // The first-login redirect to the setup guide is covered by 00_first_run;
    // here it would race the test's own navigation.
    try { sessionStorage.setItem("alertd.setupShown", "1"); } catch { /* */ }
  }, [lang, theme]);
  const page = await ctx.newPage();
  await login(page, PASSWORD);
  return page;
}

export async function login(page, password) {
  await page.goto(`${BASE}/admin/`, { waitUntil: "networkidle" });
  await page.fill("#u", "admin");
  await page.fill("#p", password);
  await page.click("button[type=submit]");
  // Either the app shell or the forced password change (#new) replaces the login form.
  await page.waitForSelector("nav.nav, #new", { state: "attached" });
  await page.waitForLoadState("networkidle").catch(() => {});
}

/** Poll `fn` until it returns truthy (Preact renders on the next frame). */
export async function until(fn, { timeout = 5000, step = 100 } = {}) {
  const end = Date.now() + timeout;
  let last;
  while (Date.now() < end) { last = await fn(); if (last) return last; await new Promise((r) => setTimeout(r, step)); }
  return last;
}

export async function go(page, route) {
  await page.goto(`${BASE}/admin/#/${route}`);
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(500);
}

/** Collect console errors, uncaught exceptions and failed requests from now on. */
export function watch(page) {
  const seen = { errors: [], failed: [] };
  // "Failed to load resource" is the browser echoing an HTTP error status;
  // those are judged below from the responses themselves.
  page.on("console", (m) => { if (m.type() === "error" && !m.text().startsWith("Failed to load resource")) seen.errors.push(m.text().slice(0, 300)); });
  page.on("pageerror", (e) => seen.errors.push(String(e).slice(0, 300)));
  // GET /v1/auth/me answers 401 before login by design.
  page.on("response", (r) => { if (r.status() >= 400 && !(r.status() === 401 && r.url().endsWith("/v1/auth/me"))) seen.failed.push(`${r.status()} ${r.request().method()} ${r.url().replace(BASE, "")}`); });
  return seen;
}

/** axe violations (WCAG 2.1 A/AA + best practice) inside `selector`. */
export async function axe(page, selector = "body") {
  await page.evaluate(AXE);
  return page.evaluate(async (sel) => {
    const r = await window.axe.run(document.querySelector(sel) || document,
      { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] } });
    return r.violations.map((v) => `${v.id} (${v.impact}) ×${v.nodes.length}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  }, selector);
}

export async function api(method, path, body, { yaml = false } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "X-API-Key": ADMIN_KEY, "Content-Type": yaml ? "application/yaml" : "application/json" },
    body: body === undefined ? undefined : (yaml ? body : JSON.stringify(body)),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : null;
}

/** Data the tests need: long-titled critical alerts (dashboard card), a rule, a variable. */
export async function seed() {
  const pack = readFileSync(fileURLToPath(new URL("./seed.json", import.meta.url)), "utf8");
  await api("POST", "/v1/config/import?apply=true", pack, { yaml: true });
  for (let i = 1; i <= 6; i++) {
    await api("POST", "/v1/fire", { type: "e2e_disk_full", context: { host: `storage-node-with-a-long-hostname-${i}`, pct: 90 + i } });
  }
  await api("POST", "/v1/fire", { type: "e2e_info", context: { what: "seed" } });
}
