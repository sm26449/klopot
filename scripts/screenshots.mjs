// README screenshots from synthetic data — run through scripts/screenshots.sh,
// which provides a throwaway install (E2E_URL…) and a local HTTP sink (SINK_URL).
// Everything below is made up: a small demo site, example.com hosts.
import { mkdirSync } from "node:fs";
import { generateKeyPairSync, randomBytes } from "node:crypto";
import { BASE, BOOTSTRAP_PASSWORD, PASSWORD, api, go, launch, login, session } from "../tests/e2e/support.mjs";

const SINK = process.env.SINK_URL;
if (!SINK) throw new Error("SINK_URL is not set — run scripts/screenshots.sh");
const OUT = new URL("../docs/screenshots/", import.meta.url);
mkdirSync(OUT, { recursive: true });
const TOKEN = "demo-input-token-" + randomBytes(8).toString("hex");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── Seed ─────────────────────────────────────────────────────────────

async function seed() {
  const vapid = generateKeyPairSync("ec", { namedCurve: "P-256" }).privateKey.export({ format: "jwk" }).d;
  for (const ch of [
    { name: "ops-webhook", kind: "webhook", config: { url: `${SINK}/hooks/ops` } },
    { name: "pager-webhook", kind: "webhook", config: { url: `${SINK}/hooks/flaky-pager` } },
    { name: "phone-ntfy", kind: "ntfy", config: { server_url: SINK, topic: "ops-alerts-demo" } },
    { name: "team-gotify", kind: "gotify", config: { server_url: SINK, app_token: "demo-gotify-app" } },
    { name: "phones", kind: "push", config: { vapid_private: vapid, vapid_subject: "mailto:ops@example.com" } },
  ]) await api("POST", "/v1/channels", ch);

  const input = await api("POST", "/v1/inputs", {
    name: "site_sensors", kind: "webhook", config: { auth_required: true, auth_token: TOKEN },
  });

  const num = (name, path, description, stale = 600) => ({
    name, source: "mqtt", input: "site_sensors", description,
    config: { topic: "webhook:site_sensors", json_path: path, type: "number", stale_after_sec: stale },
  });
  const pack = {
    version: "1.0",
    templates: [
      { type: "server_room_hot", severity: "critical", icon: "🌡️", category: "Facilities",
        title_template: "Server room at {server_room.temp}°C",
        message_template: "Above the 30°C limit for two checks. Cooling unit: {server_room.ac_state}.", min_repeat_min: 30 },
      { type: "server_room_ok", severity: "info", icon: "✅", category: "Facilities",
        title_template: "Server room back to {server_room.temp}°C", message_template: "Temperature recovered.", min_repeat_min: 0 },
      { type: "ups_on_battery", severity: "warning", icon: "🔋", category: "Power",
        title_template: "UPS on battery — {ups.battery_pct}% left",
        message_template: "Mains power lost at the rack. Estimated runtime {ups.runtime_min} min.", min_repeat_min: 30 },
      { type: "internet_slow", severity: "warning", icon: "🌐", category: "Network",
        title_template: "Internet latency {internet.latency_ms} ms", message_template: "Upstream round-trip above 150 ms.", min_repeat_min: 30 },
      { type: "backup_failed", severity: "critical", icon: "🗄️", category: "Backups",
        title_template: "Nightly backup failed on {host}", message_template: "{job}: {error}", min_repeat_min: 0 },
      { type: "disk_filling", severity: "warning", icon: "💾", category: "Infrastructure",
        title_template: "Disk {mount} on {host} at {pct}%", message_template: "{free_gb} GB free.", min_repeat_min: 0 },
      { type: "deploy_finished", severity: "info", icon: "🚀", category: "Releases",
        title_template: "Deployed {service} {version}", message_template: "Rolled out to {hosts} hosts in {duration}.", min_repeat_min: 0 },
    ],
    routes: [
      { template: "server_room_hot", channel: "ui_default", severity_min: "info" },
      { template: "server_room_hot", channel: "phone-ntfy", severity_min: "info" },
      { template: "server_room_hot", channel: "team-gotify", severity_min: "info" },
      { template: "server_room_ok", channel: "ui_default", severity_min: "info" },
      { template: "server_room_ok", channel: "phone-ntfy", severity_min: "info" },
      { template: "ups_on_battery", channel: "ui_default", severity_min: "info" },
      { template: "ups_on_battery", channel: "phone-ntfy", severity_min: "info" },
      { template: "internet_slow", channel: "ui_default", severity_min: "info" },
      { template: "backup_failed", channel: "ui_default", severity_min: "info" },
      { template: "backup_failed", channel: "ops-webhook", severity_min: "info" },
      { template: "backup_failed", channel: "pager-webhook", severity_min: "info" },
      { template: "disk_filling", channel: "ui_default", severity_min: "info" },
      { template: "disk_filling", channel: "ops-webhook", severity_min: "info" },
      { template: "deploy_finished", channel: "ui_default", severity_min: "info" },
    ],
    variables: [
      num("server_room.temp", "server_room.temp", "Rack inlet temperature, °C"),
      { name: "server_room.ac_state", source: "mqtt", input: "site_sensors", description: "Cooling unit state",
        config: { topic: "webhook:site_sensors", json_path: "server_room.ac", type: "string", stale_after_sec: 600 } },
      num("ups.battery_pct", "ups.battery", "UPS battery charge, %"),
      num("ups.runtime_min", "ups.runtime", "UPS estimated runtime, minutes"),
      { name: "ups.on_battery", source: "mqtt", input: "site_sensors", description: "UPS running on battery",
        config: { topic: "webhook:site_sensors", json_path: "ups.on_battery", type: "bool", stale_after_sec: 600 } },
      num("internet.latency_ms", "internet.latency", "Upstream round-trip, ms"),
      num("solar.power_kw", "solar.power", "PV output, kW"),
    ],
    rules: [
      { name: "server_room_hot", template_type: "server_room_hot", condition_expr: "server_room.temp > 30",
        persist_n: 2, eval_interval_sec: 5, incident_enabled: true, recovery_expr: "server_room.temp < 27",
        resolved_template_type: "server_room_ok", trigger_summary: "Rack inlet above 30°C for two checks" },
      { name: "ups_on_battery", template_type: "ups_on_battery", condition_expr: "ups.on_battery and ups.battery_pct < 90",
        persist_n: 1, eval_interval_sec: 5, trigger_summary: "UPS on battery" },
      { name: "internet_slow", template_type: "internet_slow", condition_expr: "internet.latency_ms > 150",
        persist_n: 2, eval_interval_sec: 5, trigger_summary: "Latency above 150 ms for two checks" },
      { name: "ups_battery_low", template_type: "ups_on_battery", condition_expr: "ups.battery_pct < 20",
        persist_n: 1, eval_interval_sec: 10, trigger_summary: "UPS battery below 20%" },
      { name: "solar_offline", template_type: "internet_slow", condition_expr: "var_age('solar.power_kw') > 900",
        persist_n: 3, eval_interval_sec: 60, trigger_summary: "No PV reading for 15 minutes" },
    ],
  };
  await api("POST", "/v1/config/import?apply=true", JSON.stringify(pack), { yaml: true });

  const post = (body) => fetch(`${BASE}/v1/inputs/${input.id}/webhook`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-Input-Token": TOKEN }, body: JSON.stringify(body),
  });
  const reading = (temp, onBattery, battery, latency) => ({
    server_room: { temp, ac: temp > 30 ? "fault" : "cooling" },
    ups: { on_battery: onBattery, battery, runtime: Math.round(battery * 0.6) },
    internet: { latency }, solar: { power: 4.2 },
  });
  // A calm start, then the room heats up, the UPS drops to battery and the uplink slows.
  await post(reading(24.5, false, 100, 18));
  await sleep(6000);
  for (const [t, ups, b, l] of [[31.2, true, 87, 190], [32.4, true, 84, 210], [32.8, true, 82, 205]]) {
    await post(reading(t, ups, b, l));
    await sleep(6000);
  }

  // External events through the API.
  for (const [host, mount, pct, free] of [["nas-01", "/srv", 91, 74], ["db-02", "/var/lib/mysql", 87, 112]]) {
    await api("POST", "/v1/fire", { type: "disk_filling", source: "node-exporter",
      context: { host, mount, pct, free_gb: free } });
  }
  await api("POST", "/v1/fire", { type: "backup_failed", source: "restic", idempotency_key: "backup-nas-01",
    context: { host: "nas-01", job: "restic nightly", error: "repository locked by another process" } });
  await api("POST", "/v1/fire", { type: "backup_failed", source: "restic", idempotency_key: "backup-db-02",
    context: { host: "db-02", job: "mysqldump nightly", error: "connection refused" } });
  await api("POST", "/v1/fire", { type: "backup_failed", source: "restic", idempotency_key: "backup-db-02",
    status: "resolved", context: { host: "db-02", job: "mysqldump nightly", error: "retried at 03:20 — completed" } });
  await api("POST", "/v1/fire", { type: "disk_filling", source: "node-exporter", idempotency_key: "disk-web-03",
    context: { host: "web-03", mount: "/var/log", pct: 93, free_gb: 3 } });
  for (const [svc, ver, hosts, dur] of [["api", "v4.12.0", 6, "3m 41s"], ["web", "v2.8.3", 3, "1m 12s"]]) {
    await api("POST", "/v1/fire", { type: "deploy_finished", source: "ci", context: { service: svc, version: ver, hosts, duration: dur } });
  }
  await sleep(4000);
  // One alert already handled by someone.
  const log = await api("GET", "/v1/log?limit=50");
  const deploy = (log.items || log).find((r) => r.type === "deploy_finished");
  if (deploy) await api("POST", `/v1/log/${deploy.id}/ack`);
  const incidents = await api("GET", "/v1/incidents?limit=50&state=active");
  const disk = (incidents.items || incidents).find((i) => (i.rule_name || "").includes("disk-web-03"));
  if (disk) await api("POST", `/v1/incidents/${disk.id}/ack`);
}

/** Headless Chromium never grants notifications: stand in for the browser's
 *  PushManager so the page shows this device as enabled (as tests/e2e/40_push does). */
async function stubPush(context, endpoint, keys) {
  await context.addInitScript(([ep, k]) => {
    const sub = { endpoint: ep, options: { applicationServerKey: null },
      toJSON: () => ({ endpoint: ep, expirationTime: null, keys: k }), unsubscribe: async () => true };
    Object.defineProperty(Notification, "permission", { get: () => "granted" });
    Notification.requestPermission = async () => "granted";
    PushManager.prototype.subscribe = async () => sub;
    PushManager.prototype.getSubscription = async () => sub;
  }, [endpoint, keys]);
}

async function registerDevices(page) {
  const devices = [
    ["iPhone · Safari", "warning"], ["Pixel 8 · Chrome", "critical"], ["Office desktop · Firefox", "info"],
  ];
  const registered = [];
  for (const [label, minSeverity] of devices) {
    const body = {
      endpoint: `https://fcm.googleapis.com/fcm/send/demo-${randomBytes(8).toString("hex")}`,
      keys: { p256dh: Buffer.concat([Buffer.from([4]), randomBytes(64)]).toString("base64url"), auth: randomBytes(16).toString("base64url") },
      label,
    };
    registered.push(body);
    const id = await page.evaluate(async (b) => {
      const csrf = decodeURIComponent((document.cookie.match(/alertd_csrf=([^;]+)/) || [])[1] || "");
      const r = await fetch("/v1/push/subscriptions", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(b) });
      return (await r.json()).id;
    }, body);
    if (minSeverity !== "warning") {
      await page.evaluate(async ([i, sev]) => {
        const csrf = decodeURIComponent((document.cookie.match(/alertd_csrf=([^;]+)/) || [])[1] || "");
        await fetch(`/v1/push/subscriptions/${i}`, { method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ min_severity: sev }) });
      }, [id, minSeverity]);
    }
  }
  return registered;
}

// ── Shoot ────────────────────────────────────────────────────────────

async function shot(page, name) {
  await page.locator(".toast").evaluateAll((els) => els.forEach((e) => e.remove())).catch(() => {});
  await page.waitForTimeout(400);
  await page.screenshot({ path: new URL(`${name}.png`, OUT).pathname });
  console.log(`  ${name}.png`);
}

/** The first login of a fresh install forces a password change. */
async function firstLogin(browser) {
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await login(page, BOOTSTRAP_PASSWORD);
  await page.fill("#cur", BOOTSTRAP_PASSWORD);
  await page.fill("#new", PASSWORD);
  await page.fill("#cfm", PASSWORD);
  await page.click("form button[type=submit]");
  await page.waitForSelector("nav.nav", { state: "attached" });
  await page.context().close();
}

async function main() {
  console.log("== seeding a demo site");
  await seed();
  const browser = await launch();
  try {
    await firstLogin(browser);
    console.log("== desktop");
    for (const theme of ["light", "dark"]) {
      const page = await session(browser, { theme });
      await go(page, "dashboard");
      await page.waitForTimeout(800);
      await shot(page, `dashboard-${theme}`);
      if (theme === "light") {
        const [mine] = await registerDevices(page);
        await stubPush(page.context(), mine.endpoint, mine.keys);
        await go(page, "account");
        await page.reload({ waitUntil: "networkidle" });   // init scripts run on a load, not a hash change
        await page.getByText("Office desktop · Firefox").first().waitFor();
        await shot(page, "push-devices");
        await go(page, "log");
        await page.locator("tbody tr", { hasText: "Nightly backup failed" }).first().click();
        await page.locator(".drawer").waitFor();
        await page.waitForTimeout(800);
        await shot(page, "log-delivery");
        await go(page, "rules");
        await shot(page, "rules");
        await go(page, "templates");
        await page.locator("tbody tr", { hasText: "server_room_hot" }).first().click();
        await page.locator(".drawer").waitFor();
        await page.waitForTimeout(800);
        await shot(page, "template-editor");
        await go(page, "incidents");
        await shot(page, "incidents");
        await go(page, "activity?tab=attempts");
        await page.waitForTimeout(600);
        await shot(page, "activity");
      }
      await page.context().close();
    }
    // The dashboard on a phone (Pixel 7): klopot.dev shows it on narrow
    // screens, where the desktop shot shrinks past reading.
    console.log("== phone");
    for (const theme of ["light", "dark"]) {
      const page = await session(browser, { theme, phone: true });
      await go(page, "dashboard");
      await page.waitForTimeout(800);
      await shot(page, `dashboard-phone-${theme}`);
      await page.context().close();
    }
  } finally {
    await browser.close();
  }
}

await main();
