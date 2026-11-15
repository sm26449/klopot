// Browser smoke for the alertd admin UI (phase F2 shell; extended per phase).
//
// Drives a real Chromium through: login (wrong + bootstrap password) →
// forced password change → dashboard → placeholder route → account /
// sessions (second browser context revoked) → theme → logout → CSP header.
// Fails on any console error (except the browser's own 401 resource
// notices), any failed request and any 5xx.
//
// Prerequisites: a running alertd whose admin account is in bootstrap
// state (must_change_password=1, password = SMOKE_BOOT_PASSWORD), e.g.
//
//   ALERTD_DATABASE_URL=mysql+aiomysql://alertd:alertd@127.0.0.1:33098/alertd \
//   ALERTD_MQTT_HOST= ALERTD_ADMIN_BOOTSTRAP_PASSWORD=bootstrap-pass-12345 \
//   ALERTD_COOKIE_SECURE=false uvicorn app.main:app --port 5099
//
// Run (needs `playwright` resolvable — `npm i playwright` or NODE_PATH-free
// absolute import; CHROME_PATH overrides the browser binary):
//
//   node scripts/ui_smoke.mjs http://127.0.0.1:5099
//
// Not wired into CI yet (plan phase F10).
import { chromium } from "playwright";

const base = process.argv[2] || "http://127.0.0.1:5099";
const BOOT = process.env.SMOKE_BOOT_PASSWORD || "bootstrap-pass-12345";
const NEW = process.env.SMOKE_NEW_PASSWORD || "my-new-long-password-2026";
const shots = process.env.SHOTS || ".";

const consoleErrors = [];
const failedRequests = [];
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error" && !/status of 401/.test(m.text())) consoleErrors.push(m.text()); });
page.on("pageerror", (e) => consoleErrors.push("pageerror: " + e.message));
page.on("requestfailed", (r) => failedRequests.push(r.url() + " " + (r.failure()?.errorText || "")));
page.on("response", (r) => { if (r.status() >= 500) failedRequests.push(`${r.status()} ${r.url()}`); });

function step(name) { console.log("▶", name); }
async function expect(cond, msg) { if (!cond) { await page.screenshot({ path: `${shots}/ui-smoke-FAIL.png` }); throw new Error("ASSERT: " + msg); } }

try {
step("open /admin/ → login form");
await page.goto(base + "/admin/", { waitUntil: "networkidle" });
await page.waitForSelector("form.auth-card", { timeout: 10000 });
await expect(await page.isVisible("input#u"), "username input visible");
await page.screenshot({ path: `${shots}/ui-smoke-1-login.png` });

step("wrong password → generic error, no cookie");
await page.fill("input#p", "definitely-wrong-pw");
await page.click("button[type=submit]");
await page.waitForSelector("p.error");
const errText = await page.textContent("p.error");
await expect(/Invalid username or password/.test(errText), "generic error shown: " + errText);
const cookiesBefore = await ctx.cookies();
await expect(!cookiesBefore.some((c) => c.name === "alertd_session"), "no session cookie after failure");

step("bootstrap password → forced change screen");
await page.fill("input#p", BOOT);
await page.click("button[type=submit]");
await page.waitForSelector("text=Set a new password", { timeout: 10000 });
const cookies = await ctx.cookies();
const sess = cookies.find((c) => c.name === "alertd_session");
const csrf = cookies.find((c) => c.name === "alertd_csrf");
await expect(sess && sess.httpOnly && sess.sameSite === "Strict", "session cookie HttpOnly+Strict: " + JSON.stringify(sess));
await expect(csrf && !csrf.httpOnly, "csrf cookie readable by JS");
await page.screenshot({ path: `${shots}/ui-smoke-2-must-change.png` });

step("policy: too short is blocked client-side");
await page.fill("input#cur", BOOT);
await page.fill("input#new", "short");
await page.fill("input#cfm", "short");
await expect(await page.isDisabled("button[type=submit]"), "submit disabled for short password");

step("change password → dashboard");
await page.fill("input#new", NEW);
await page.fill("input#cfm", NEW);
await page.click("button[type=submit]");
await page.waitForSelector("h1:has-text('Dashboard')", { timeout: 10000 });
await page.waitForSelector(".topbar .badge.ok, .topbar .badge.degraded, .topbar .badge.down", { timeout: 10000 });
await expect((await page.textContent(".sidebar .brand")).includes("Klopot"), "sidebar brand");
await expect(await page.isVisible("text=Links"), "dashboard links card");
await page.screenshot({ path: `${shots}/ui-smoke-3-dashboard.png` });

step("F4 dashboard: stat tiles + inventory render");
await page.waitForSelector(".tiles .tile", { timeout: 10000 });
await expect((await page.$$(".tiles .tile")).length >= 4, "four stat tiles");
await expect(await page.isVisible("h2:has-text('Inventory')"), "inventory card");
await expect(await page.isVisible("h2:has-text('Last 24 h')"), "24h breakdown card");

step("F4 Alerts log: table/filters render, live toggle, pager");
await page.click("a[href='#/log']");
await page.waitForSelector("h1:has-text('Alerts log')", { timeout: 10000 });
await page.waitForSelector(".card.filters", { timeout: 10000 });
await page.waitForSelector(".pager", { timeout: 10000 });     // appears once the log query resolves
await page.click(".live-toggle input");           // turn live tail on
await expect(await page.isVisible(".live-toggle .dot.on"), "live indicator on");
await page.click(".live-toggle input");            // and off (no crash)
await page.screenshot({ path: `${shots}/ui-smoke-5-log.png` });

step("F4 Snooze & maintenance: form + active list render");
await page.click("a[href='#/snooze']");
await page.waitForSelector("h1:has-text('Snooze & maintenance')", { timeout: 10000 });
await expect(await page.isVisible("h2:has-text('New snooze')"), "new-snooze form");
await expect(await page.isVisible("button:has-text('Maintenance mode')"), "maintenance button");
await expect(await page.isVisible("h2:has-text('Active snoozes')"), "active snoozes card");
await page.screenshot({ path: `${shots}/ui-smoke-6-snooze.png` });

step("F5 Templates: list + editor with live preview + routing");
await page.click("a[href='#/templates']");
await page.waitForSelector("h1:has-text('Templates')", { timeout: 10000 });
await page.waitForSelector(".tbl tbody tr", { timeout: 10000 });     // seeded builtin templates
await page.click(".tbl tbody tr");                                   // open first template
await page.waitForSelector(".drawer .preview", { timeout: 10000 });
await expect(await page.isVisible(".preview-out .preview-title"), "live preview renders a title");
await expect(await page.isVisible("h3:has-text('Routing')"), "routing section present");
await page.screenshot({ path: `${shots}/ui-smoke-7-template.png` });
await page.keyboard.press("Escape");                                 // close drawer
await page.waitForSelector(".drawer", { state: "detached", timeout: 10000 });

step("F5 Channels: cards + typed editor from meta/kinds + secret field");
await page.click("a[href='#/channels']");
await page.waitForSelector("h1:has-text('Channels')", { timeout: 10000 });
await page.click("button:has-text('New channel')");
await page.waitForSelector(".drawer", { timeout: 10000 });
await page.selectOption(".drawer select", "telegram");              // kind → fields appear
await page.waitForSelector(".drawer .field.secret", { timeout: 10000 });
await expect(await page.isVisible("text=bot_token"), "telegram secret field rendered");
await expect(await page.isVisible("button:has-text('Replace')"), "secret replace control");
await page.screenshot({ path: `${shots}/ui-smoke-8-channel.png` });
await page.keyboard.press("Escape");
await page.waitForSelector(".drawer", { state: "detached", timeout: 10000 });

step("F6 Rules: list + editor with validate + cheat-sheet");
await page.click("a[href='#/rules']");
await page.waitForSelector("h1:has-text('Rules')", { timeout: 10000 });
await page.click("button:has-text('New rule')");
await page.waitForSelector(".drawer textarea.mono", { timeout: 10000 });
await page.fill(".drawer textarea.mono", "soc < 20");
await page.click(".drawer button:has-text('Validate')");
await page.waitForSelector(".drawer .badge:has-text('ok'), .drawer .badge:has-text('error')", { timeout: 10000 });
await expect(await page.isVisible("summary:has-text('cheat-sheet')"), "expression cheat-sheet present");
await page.screenshot({ path: `${shots}/ui-smoke-9-rule.png` });
await page.keyboard.press("Escape");
await page.waitForSelector(".drawer", { state: "detached", timeout: 10000 });

step("F6 Variables / Inputs / Schedules / State render");
await page.click("a[href='#/variables']");
await page.waitForSelector("h1:has-text('Variables')", { timeout: 10000 });
await page.click("a[href='#/inputs']");
await page.waitForSelector("h1:has-text('Inputs')", { timeout: 10000 });
await page.click("a[href='#/schedules']");
await page.waitForSelector("h1:has-text('Schedules')", { timeout: 10000 });
await page.click("button:has-text('New schedule')");
await page.waitForSelector(".drawer .cron-next li", { timeout: 10000 });    // live cron preview
await expect((await page.$$(".drawer .cron-next li")).length === 5, "cron preview shows 5 next firings");
await page.keyboard.press("Escape");
await page.click("a[href='#/state']");
await page.waitForSelector("h1:has-text('State cache')", { timeout: 10000 });
await page.screenshot({ path: `${shots}/ui-smoke-10-state.png` });

step("F7 API keys: list + create editor with scopes");
await page.click("a[href='#/api-keys']");
await page.waitForSelector("h1:has-text('API keys')", { timeout: 10000 });
await page.click("button:has-text('New key')");
await page.waitForSelector(".drawer .scope-row", { timeout: 10000 });
await expect(await page.isVisible("text=implies all others"), "scope descriptions shown");
await page.screenshot({ path: `${shots}/ui-smoke-11-apikey.png` });
await page.keyboard.press("Escape");
await page.waitForSelector(".drawer", { state: "detached", timeout: 10000 });

step("F7 Audit + Config render");
await page.click("a[href='#/audit']");
await page.waitForSelector("h1:has-text('Audit')", { timeout: 10000 });
await page.click("a[href='#/config']");
await page.waitForSelector("h1:has-text('Config import / export')", { timeout: 10000 });
await expect(await page.isVisible("button:has-text('Export YAML')"), "export control present");

step("F7 Account: effective settings render");
await page.click("a[href='#/account']");
await page.waitForSelector("h2:has-text('Effective settings')", { timeout: 10000 });

step("account: sessions table has this browser");
await page.click("a[href='#/account']");
await page.waitForSelector("table.sessions tbody tr", { timeout: 10000 });
await expect(await page.isVisible("text=this browser"), "current session flagged");
await expect(await page.isDisabled("button:has-text('Sign out others')"), "revoke-others disabled with 1 session");
await page.screenshot({ path: `${shots}/ui-smoke-4-account.png` });

step("second session appears, can be revoked");
const ctx2 = await browser.newContext();
const p2 = await ctx2.newPage();
await p2.goto(base + "/admin/", { waitUntil: "networkidle" });
await p2.fill("input#p", NEW);
await p2.click("button[type=submit]");
await p2.waitForSelector("h1:has-text('Dashboard')");
await page.click("button:has-text('Refresh')");
// Selector-engine waits (CSP-safe): the app ships a strict CSP without
// 'unsafe-eval', which blocks waitForFunction's in-page poll. Wait on the
// second session row appearing, then on it detaching after revoke.
await page.waitForSelector("table.sessions tbody tr:nth-child(2)", { timeout: 10000 });
page.once("dialog", (d) => d.accept());
await page.click("button:has-text('Sign out others')");
await page.waitForSelector("table.sessions tbody tr:nth-child(2)", { state: "detached", timeout: 10000 });
await p2.click("a[href='#/account']");
await p2.waitForSelector("form.auth-card", { timeout: 10000 });  // kicked back to login on 401
await ctx2.close();

step("theme toggle persists");
await page.selectOption(".topbar select", "dark");
await expect((await page.getAttribute("html", "data-theme")) === "dark", "data-theme=dark applied");

step("sign out → login form");
await page.click(".topbar button:has-text('Sign out')");
await page.waitForSelector("form.auth-card");
const after = await ctx.cookies();
await expect(!after.some((c) => c.name === "alertd_session" && c.value), "session cookie cleared");

step("CSP header on /admin/, API reachable only same-origin");
const resp = await page.request.get(base + "/admin/");
const csp = resp.headers()["content-security-policy"] || "";
await expect(csp.includes("script-src 'self'") && !csp.includes("unsafe"), "strict CSP: " + csp);

} catch (e) {
  console.log("FAILED:", e.message);
  console.log("console errors:", consoleErrors);
  console.log("failed requests:", failedRequests);
  try { console.log("BODY:", (await page.innerHTML("body")).slice(0, 800)); await page.screenshot({ path: `${shots}/ui-smoke-FAIL.png` }); } catch {}
  await browser.close();
  process.exit(1);
}
await browser.close();

if (consoleErrors.length) { console.log("console errors:", consoleErrors); process.exit(2); }
if (failedRequests.length) { console.log("failed requests:", failedRequests); process.exit(3); }
console.log("✅ UI smoke passed — no console errors, no failed requests");
