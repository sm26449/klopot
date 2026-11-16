// Behaviour the audit flagged: toasts outlive the page, validation only in a
// toast, clipped dashboard cards, drawers with an invalid role.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { launch, session, go, until, axe, api } from "./support.mjs";

let browser, page;
before(async () => { browser = await launch(); page = await session(browser, { lang: "en" }); page.on("dialog", (d) => d.accept()); });
after(async () => { await browser?.close(); });

test("dashboard: unacknowledged criticals fit their card and offer Ack", async () => {
  await go(page, "dashboard");
  const rows = page.locator(".crit-list li");
  await until(async () => (await rows.count()) > 0);
  const clip = await page.evaluate(() => [...document.querySelectorAll("main .card")]
    .map((c) => c.scrollWidth - c.clientWidth).filter((d) => d > 1));
  assert.deepEqual(clip, [], "cards clip their content horizontally");
  const ack = rows.first().getByRole("button", { name: /ack/i });
  assert.ok(await ack.isVisible(), "Ack is visible");
  const box = await ack.boundingBox();
  assert.ok(box.x + box.width <= 1440, "Ack is inside the viewport");
});

test("a toast does not follow you to the next page", async () => {
  await go(page, "dashboard");
  await page.evaluate(() => import("./lib/toast.js").then((m) => m.toast.ok("e2e toast")));
  await until(() => page.locator(".toast").count());
  await go(page, "rules");
  assert.equal(await page.locator(".toast", { hasText: "e2e toast" }).count(), 0);
});

for (const route of ["templates", "channels", "rules", "variables", "inputs", "schedules"]) {
  test(`${route}: saving an empty form marks the fields inline`, async () => {
    await go(page, route);
    await page.click(".page-head .actions .btn.primary");
    const drawer = page.locator(".drawer");
    await drawer.waitFor();
    assert.deepEqual(await axe(page, ".drawer"), [], "drawer axe");
    // A new channel starts with the kind picker: nothing to save yet.
    const save = drawer.locator(".btn.primary").last();
    if (await save.count() && await save.isEnabled()) {
      await save.click();
      const marked = await until(() => drawer.locator("[aria-invalid=true]").count());
      assert.ok(marked > 0, "at least one field is marked invalid");
      // Focus goes to the error summary (its entries jump to each field).
      // Preact moves focus in an effect on the next frame — poll (docs/ADMIN_UI.md, Testing).
      const focused = await until(() => page.evaluate(() => document.activeElement?.matches(".field-error-summary, [aria-invalid=true]")));
      assert.ok(focused, "focus moves to the error summary");
      assert.equal(await page.locator(".toast.error").count(), 0, "no error toast for a form mistake");
    }
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
  });
}

test("templates: a half-filled delivery gate is flagged, a full one is saved", async () => {
  await go(page, "templates");
  await page.locator("tbody tr", { hasText: "e2e_info" }).first().click();
  const drawer = page.locator(".drawer");
  await drawer.waitFor();
  await page.fill("#t-gatemin", "20");
  await drawer.locator(".btn.primary").last().click();
  assert.ok(await until(() => page.locator("#t-gatevar[aria-invalid=true]").count()), "variable marked as missing");
  await page.fill("#t-gatevar", "e2e.temperature");
  await drawer.locator(".btn.primary").last().click();
  await until(async () => (await page.locator(".drawer").count()) === 0 || (await page.locator(".toast.ok").count()) > 0);
  const tpl = await api("GET", "/v1/templates/e2e_info");
  assert.equal(tpl.gate_variable, "e2e.temperature");
  assert.equal(tpl.gate_min, 20);
  assert.equal(tpl.require_pv_kw, 20, "deprecated alias mirrors gate_min");
  await api("PATCH", "/v1/templates/e2e_info", { gate_variable: null, gate_min: null });
  await page.keyboard.press("Escape");
});

test("channels: the SMS form shows only the chosen provider's fields", async () => {
  await go(page, "channels");
  await page.click(".page-head .actions .btn.primary");
  await page.locator(".drawer").waitFor();
  // A new channel starts with the kind picker (cards), then the form.
  await page.locator(".kind-card", { hasText: "SMS" }).click();
  await page.fill("#ch-name", "e2e_sms");
  assert.ok(await page.locator("#f_url").isVisible(), "http is the default provider");
  assert.equal(await page.locator("#f_account_sid").count(), 0, "no Twilio fields for http");
  await page.selectOption("#f_provider", "twilio");
  await until(() => page.locator("#f_account_sid").count());
  assert.equal(await page.locator("#f_url").count(), 0, "http fields hidden for twilio");
  await page.selectOption("#f_provider", "http");
  await page.fill("#f_phone", "+15555550100");
  await page.fill("#f_url", "http://sms.example.invalid/send");
  await page.locator(".drawer .btn.primary").last().click();
  await until(async () => (await page.locator(".drawer").count()) === 0);
  const ch = (await api("GET", "/v1/channels?limit=500")).items.find((c) => c.name === "e2e_sms");
  assert.equal(ch.config.provider, "http");
  assert.equal(ch.config.account_sid, undefined, "hidden fields are not saved");
  await api("DELETE", `/v1/channels/${ch.id}`);
});

test("packs: install a catalog pack with its settings from the UI", async () => {
  await go(page, "packs");
  const card = page.locator(".pack-card", { hasText: /Sensor above a threshold/ });
  await card.getByRole("button", { name: /install/i }).click();
  const drawer = page.locator(".drawer");
  await drawer.waitFor();
  await page.fill("#pp-key", "e2e_probe");
  await page.fill("#pp-threshold", "42");
  await page.fill("#pp-broker_port", "1.5");              // the server wants an integer
  await drawer.getByRole("button", { name: /preview/i }).click();
  assert.ok(await until(() => page.locator("#pp-broker_port[aria-invalid=true]").count()), "port marked invalid");
  await page.fill("#pp-broker_port", "1883");
  await drawer.getByRole("button", { name: /preview/i }).click();
  await until(() => drawer.locator(".import-section").count());
  assert.deepEqual(await axe(page, ".drawer"), [], "install drawer axe");
  await drawer.locator(".form-actions .btn.primary").last().click();
  await until(() => drawer.getByText(/pack installed/i).count());
  const rule = (await api("GET", "/v1/rules?limit=500")).items.find((r) => r.name === "e2e_probe_above_threshold");
  assert.ok(rule && rule.condition_expr.endsWith("e2e_probe_value > 42"), "rule installed with the chosen threshold");
});

test("search: Ctrl+K finds a page and an item, Enter opens it", async () => {
  await go(page, "dashboard");
  await page.keyboard.press("Control+k");
  const input = page.getByRole("combobox", { name: /search klopot/i });
  await input.waitFor();
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("role")), "combobox", "focus is in the search box");
  await input.fill("e2e_temperature");
  await page.getByRole("option", { name: /e2e_temperature_high/ }).waitFor();
  assert.deepEqual(await axe(page, ".palette"), [], "palette axe");
  await enterOpens(/#\/rules\/\d+/);
  await page.locator(".drawer").waitFor();          // the rule's editor opened
  await page.keyboard.press("Escape");
  await page.locator(".drawer").waitFor({ state: "detached" });
  await page.keyboard.press("Control+k");
  await input.fill("chanels");                     // a typo still finds the page
  // Wait for the new results: Enter on the previous list would open the old item.
  const fresh = await until(async () => /channel/i.test(await page.locator(".palette [role=option][aria-selected=true]").innerText().catch(() => "")));
  assert.ok(fresh, "the typo search selects the channels entry");
  await enterOpens(/#\/channels/);
});

/** Press Enter in the palette and wait for `url`; on a timeout, say what the
 *  palette showed, where focus was and where the page went. */
async function enterOpens(url) {
  const state = () => page.evaluate(() => ({
    highlighted: document.querySelector(".palette [role=option][aria-selected=true]")?.innerText?.replace(/\s+/g, " "),
    options: document.querySelectorAll(".palette [role=option]").length,
    focus: document.activeElement?.className || document.activeElement?.tagName,
    open: !!document.querySelector(".palette"),
    url: location.hash,
  }));
  const before = await state();
  await page.keyboard.press("Enter");
  const reached = await until(() => url.test(page.url()), { timeout: 10000 });
  assert.ok(reached, `Enter did not open ${url}: before ${JSON.stringify(before)}, after ${JSON.stringify(await state())}`);
}

test("empty states: a filter with no match offers to clear it", async () => {
  await go(page, "rules");
  await page.goto(`${process.env.E2E_URL}/admin/#/rules?search=no-such-rule-xyz`);
  const clear = page.getByRole("button", { name: /clear filters/i });
  await clear.waitFor();
  await clear.click();
  await until(async () => (await page.locator("tbody tr").count()) > 0);
  assert.equal(new URL(page.url()).hash.includes("search="), false, "the filter left the URL");
});

test("activity: requests are recorded, an ignore rule hides them but counts them", async () => {
  // A request from a "script" with the bootstrap key, then look for it.
  await api("GET", "/v1/schedules");
  await page.waitForTimeout(1500);                      // the writer batches every second
  await go(page, "activity?tab=requests&search=%2Fv1%2Fschedules");
  await until(() => page.locator("tbody tr").count());
  assert.match(await page.locator("tbody tr").first().innerText(), /GET\s+\/v1\/schedules/);
  assert.deepEqual(await axe(page, "main"), [], "requests tab axe");

  // Ignore further reads of /v1/schedules from the Rules tab.
  await go(page, "activity?tab=rules");
  await page.getByRole("button", { name: /new rule/i }).click();
  const drawer = page.locator(".drawer");
  await drawer.waitFor();
  await page.fill("#ar-name", "e2e ignore schedules");
  await page.selectOption("#ar-match_method", "GET");
  await page.fill("#ar-match_path", "/v1/schedules*");
  await page.selectOption("#ar-action", "ignore");
  await drawer.getByRole("button", { name: /preview/i }).click();
  await drawer.getByText(/would match [1-9]/i).waitFor();
  assert.deepEqual(await axe(page, ".drawer"), [], "rule drawer axe");
  await drawer.getByRole("button", { name: /^create$/i }).click();
  await until(async () => (await page.locator(".drawer").count()) === 0);
  await page.waitForTimeout(1100);                      // rule cache picks the change up at once (invalidated)

  for (let i = 0; i < 3; i++) await api("GET", "/v1/schedules");
  await page.waitForTimeout(1500);
  await go(page, "activity?tab=sources");
  const ignored = page.locator(".card", { hasText: /ignored, but counted/i });
  await ignored.waitFor();
  assert.match(await ignored.innerText(), /e2e ignore schedules[\s\S]*\b3\b/);
});

test("log drawer: the delivery timeline of an alert", async () => {
  await go(page, "log");
  await page.locator("tbody tr button.cell-btn").first().click();
  const drawer = page.locator(".drawer");
  await drawer.waitFor();
  await drawer.getByRole("heading", { name: /attempts to the providers/i }).waitFor();
  await until(() => drawer.locator(".attempts > li, .attempts + p, p.muted").count());
  assert.deepEqual(await axe(page, ".drawer"), [], "log drawer axe");
  await page.keyboard.press("Escape");
});

test("desktop shows health and search once (top bar), not again in the side menu", async () => {
  await go(page, "dashboard");
  const visible = async (sel) => page.locator(sel).evaluateAll((els) => els.filter((e) => e.getClientRects().length && getComputedStyle(e).display !== "none").length);
  assert.equal(await visible(".sidebar .brand-health"), 0, "no health badge in the side menu");
  assert.equal(await visible(".sidebar .search-phone"), 0, "no search button in the side menu");
  assert.equal(await visible(".topbar .search-bar"), 1, "search in the top bar");
  assert.equal(await visible(".topbar .health .badge"), 1, "health in the top bar");
});

test("packs: every catalog card has Install at its bottom-right corner", async () => {
  await go(page, "packs");
  await until(async () => (await page.locator(".pack-card").count()) > 1);
  const gaps = await page.locator(".pack-card").evaluateAll((cards) => cards.map((c) => {
    const card = c.getBoundingClientRect(), btn = c.querySelector(".pack-foot .btn").getBoundingClientRect();
    return Math.round(card.right - btn.right);
  }));
  assert.equal(new Set(gaps).size, 1, `same right inset on every card: ${gaps}`);
});

test("activity rules: rows are numbered 1, 2 … and the plural reads right", async () => {
  await go(page, "activity?tab=rules");
  await until(async () => (await page.locator(".tbl tbody tr").count()) > 0);
  const first = await page.locator(".tbl tbody tr").first().locator("td").first().innerText();
  assert.equal(first.trim(), "1");
  assert.ok(!(await page.locator(".tbl").innerText()).includes("(s)"), "no day(s)");
});

test("api keys: a key limited to my address and a rate, labelled and accessible", async () => {
  await go(page, "api-keys");
  await page.getByRole("button", { name: /new key/i }).first().click();
  const drawer = page.locator(".drawer");
  await drawer.waitFor();
  const field = drawer.getByLabel("Allowed addresses");
  assert.ok(await field.isVisible(), "the allowlist field has a label");
  const mine = drawer.getByRole("button", { name: /add my address/i });
  await mine.waitFor();
  await mine.click();
  const typed = (await field.inputValue()).trim();
  assert.match(typed, /^[0-9a-f.:]+$/i, "my address was filled in");
  assert.equal(await mine.isDisabled(), true, "it is not offered twice");
  await drawer.getByLabel("Requests per minute").fill("120");
  assert.deepEqual(await axe(page, ".drawer"), [], "drawer axe");
  await drawer.locator("#k-name").fill("e2e_allowlisted");
  await drawer.getByRole("button", { name: /create/i }).click();
  const shown = page.getByRole("dialog").filter({ hasText: /e2e_allowlisted/ });
  await shown.waitFor();
  const keys = await api("GET", "/v1/api_keys");
  const made = keys.items.find((k) => k.name === "e2e_allowlisted");
  assert.equal(made.allowed_cidrs.length, 1);
  assert.ok(made.allowed_cidrs[0].startsWith(typed.split("/")[0]), made.allowed_cidrs[0]);
  assert.equal(made.rate_limit_per_min, 120);
  await shown.getByRole("checkbox").check();          // "I have saved it" — the key is shown once
  await shown.getByRole("button", { name: /done/i }).click();
  const cell = page.getByRole("cell", { name: "1 allowed 120/min" });
  assert.ok(await until(async () => (await cell.count()) > 0), "the list shows both restrictions");
});
