// A fresh install: bootstrap password → forced change → app shell. Runs first —
// every later file logs in with E2E_PASSWORD, which this test sets.
import { test } from "node:test";
import assert from "node:assert/strict";
import { launch, login, seed, watch, BOOTSTRAP_PASSWORD, PASSWORD } from "./support.mjs";

test("first login forces a password change, then opens the dashboard", async () => {
  const browser = await launch();
  try {
    const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    const seen = watch(page);
    await login(page, BOOTSTRAP_PASSWORD);
    assert.ok(await page.locator("#new").count(), "the forced password change is shown");
    assert.equal(await page.locator("nav.nav").count(), 0, "no app shell before the password is changed");
    await page.fill("#cur", BOOTSTRAP_PASSWORD);
    await page.fill("#new", PASSWORD);
    await page.fill("#cfm", PASSWORD);
    await page.click("form button[type=submit]");
    await page.waitForSelector("nav.nav", { state: "attached" });

    // A fresh install opens the setup guide.
    await page.waitForURL(/#\/setup/);
    await page.getByRole("heading", { level: 1, name: /set up klopot/i }).waitFor();
    await page.getByRole("button", { name: /^start$/i }).click();
    // Step 2: no channel yet — skip, alerts stay in the admin UI.
    await page.getByRole("button", { name: /skip for now/i }).click();
    // Step 3: "my scripts" installs templates, creates a key, shows a curl.
    await page.getByRole("button", { name: /set it up/i }).click();
    await page.locator(".key-once pre").waitFor();
    assert.match(await page.locator(".key-once pre").innerText(), /X-API-Key: alertd_/);
    await page.getByRole("button", { name: /send my first alert/i }).click();
    await page.getByText(/sent to: ui_default/i).waitFor();
    await page.getByRole("button", { name: /^next$/i }).click();
    // Step 4: the checklist reflects what happened.
    const done = await page.locator(".checklist li.done").count();
    assert.ok(done >= 3, `source, rules and first alert are ticked (${done})`);
    assert.deepEqual(seen.errors, [], "no console errors");
  } finally {
    await browser.close();
  }
});

test("seed data for the later files", async () => {
  await seed();
});
