// alertd admin — application shell (phase F2).
//
// Auth state machine:
//   boot → GET /v1/auth/me
//     401            → <Login>
//     must_change    → <ChangePassword>  (API refuses other writes anyway)
//     ok             → <Shell> with the hash-routed views
// Any later 401 from the API (session expired / revoked) drops back to <Login>.

import { html, render, useEffect, useState, useCallback } from "./lib/h.js";
import { api, on as onApiEvent } from "./lib/api.js";
import { useRoute, resolve, navigate } from "./lib/router.js";
import { Toasts, toast } from "./lib/toast.js";
import { t, getLang, setLang, LANGS } from "./lib/i18n.js";
import { Wordmark, BrandIcon } from "./lib/brand.js";
import { Modal, ErrorState } from "./lib/ui.js";
import { skipToMain } from "./lib/a11y.js";
import { stackTables } from "./lib/stack_tables.js";
import { CHANGELOG } from "./changelog.js";
import { LoginView } from "./views/login.js";
import { ChangePasswordView } from "./views/password.js";
import { DashboardView } from "./views/dashboard.js";
import { LogView } from "./views/log.js";
import { IncidentsView } from "./views/incidents.js";
import { SnoozeView } from "./views/snooze.js";
import { TemplatesView } from "./views/templates.js";
import { ChannelsView } from "./views/channels.js";
import { RulesView } from "./views/rules.js";
import { VariablesView } from "./views/variables.js";
import { InputsView } from "./views/inputs.js";
import { SchedulesView } from "./views/schedules.js";
import { StateView } from "./views/state.js";
import { OperationsView } from "./views/operations.js";
import { ApiKeysView } from "./views/apikeys.js";
import { ApiView } from "./views/api.js";
import { AuditView } from "./views/audit.js";
import { ConfigView } from "./views/config.js";
import { PacksView } from "./views/packs.js";
import { ActivityView } from "./views/activity.js";
import { SetupView } from "./views/setup.js";
import { CommandPalette } from "./lib/palette.js";
import { AccountView } from "./views/account.js";
import { PlaceholderView } from "./views/placeholder.js";
import { statusLabel, componentLabel } from "./lib/labels.js";

// ── Navigation (every section of the plan; placeholders until built) ──
const NAV = [
  { titleKey: "navGroup.overview", items: [
    { path: "/dashboard", labelKey: "nav.dashboard", view: DashboardView },
    { path: "/log", labelKey: "nav.log", view: LogView },
    { path: "/incidents", labelKey: "nav.incidents", view: IncidentsView },
    { path: "/snooze", labelKey: "nav.snooze", view: SnoozeView },
  ]},
  { titleKey: "navGroup.configuration", items: [
    { path: "/templates", labelKey: "nav.templates", view: TemplatesView },
    { path: "/channels", labelKey: "nav.channels", view: ChannelsView },
    { path: "/rules", labelKey: "nav.rules", view: RulesView },
    { path: "/variables", labelKey: "nav.variables", view: VariablesView },
    { path: "/inputs", labelKey: "nav.inputs", view: InputsView },
    { path: "/schedules", labelKey: "nav.schedules", view: SchedulesView },
    { path: "/packs", labelKey: "nav.packs", view: PacksView },
  ]},
  { titleKey: "navGroup.system", items: [
    { path: "/setup", labelKey: "nav.setup", view: SetupView },
    { path: "/operations", labelKey: "nav.operations", view: OperationsView },
    { path: "/state", labelKey: "nav.state", view: StateView },
    { path: "/api-keys", labelKey: "nav.apiKeys", view: ApiKeysView },
    { path: "/api", labelKey: "nav.api", view: ApiView },
    { path: "/activity", labelKey: "nav.activity", view: ActivityView },
    { path: "/audit", labelKey: "nav.audit", view: AuditView },
    { path: "/config", labelKey: "nav.config", view: ConfigView },
    { path: "/account", labelKey: "nav.account", view: AccountView },
  ]},
];

const ROUTES = NAV.flatMap((g) => g.items).map((it) => ({
  path: it.path,
  render: it.view
    ? (props) => html`<${it.view} ...${props} />`
    : (props) => html`<${PlaceholderView} title=${t(it.labelKey)} phase=${it.soon} blurb=${it.blurb} api=${it.api} ...${props} />`,
}));
// Deep-link to a single rule (e.g. from an alert's "rule #N" link): renders the
// Rules view, which opens that rule's editor from the :id param (UX-014).
ROUTES.push({ path: "/rules/:id", labelKey: "nav.rules", render: (props) => html`<${RulesView} ...${props} />` });
ROUTES.push({ path: "/incidents/:id", labelKey: "nav.incidents", render: (props) => html`<${IncidentsView} ...${props} />` });

// ── Theme (family × mode, ADR-0002) ──────────────────────────────
// Klopot is the default family and keeps the legacy data-theme contract
// ("" = auto → OS, "light", "dark"). The OS families resolve to a concrete
// "<family>-<mode>" variant (styles.css has a token block for each).
const THEME_FAMILIES = [
  { id: "klopot", label: "Klopot" },
  { id: "macos", label: "macOS" },
  { id: "win", label: "Windows" },
  { id: "gnome", label: "GNOME" },
  { id: "kde", label: "KDE" },
];
const FAMILY_IDS = new Set(THEME_FAMILIES.map((f) => f.id));
const THEME_MODES = new Set(["auto", "light", "dark"]);

function readFamily() {
  try { const f = localStorage.getItem("alertd.family"); return FAMILY_IDS.has(f) ? f : "klopot"; }
  catch { return "klopot"; }
}
function readMode() {
  try { const m = localStorage.getItem("alertd.theme"); return THEME_MODES.has(m) ? m : "auto"; }
  catch { return "auto"; }
}
function systemDark() {
  try { return window.matchMedia("(prefers-color-scheme: dark)").matches; } catch { return false; }
}
function resolveTheme(family, mode) {
  // Klopot-auto stays "" so the @media rule drives light/dark exactly as before.
  if (family === "klopot") return mode === "auto" ? "" : mode;
  const dark = mode === "auto" ? systemDark() : mode === "dark";
  return `${family}-${dark ? "dark" : "light"}`;
}
function applyTheme(family, mode) {
  const v = resolveTheme(family, mode);
  if (v) document.documentElement.setAttribute("data-theme", v);
  else document.documentElement.removeAttribute("data-theme");
  try {
    localStorage.setItem("alertd.family", family);
    localStorage.setItem("alertd.theme", mode);
  } catch { /* private mode */ }
}

// ── Shell ────────────────────────────────────────────────────────
const LABEL_KEY_BY_PATH = Object.fromEntries(
  NAV.flatMap((g) => g.items).map((it) => [it.path, it.labelKey]),
);

function Shell({ user, health, version, onLogout, refreshMe, lang, onLangChange }) {
  const route = useRoute();
  const [family, setFamily] = useState(readFamily);
  const [mode, setMode] = useState(readMode);
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => applyTheme(family, mode), [family, mode]);
  // Re-resolve when the OS flips light/dark while we follow it (auto).
  useEffect(() => {
    if (mode !== "auto") return undefined;
    let mq;
    try { mq = window.matchMedia("(prefers-color-scheme: dark)"); } catch { return undefined; }
    const on = () => applyTheme(family, mode);
    mq.addEventListener ? mq.addEventListener("change", on) : mq.addListener(on);
    return () => { mq.removeEventListener ? mq.removeEventListener("change", on) : mq.removeListener(on); };
  }, [family, mode]);
  // Collapse the mobile nav after navigating.
  useEffect(() => { setNavOpen(false); }, [route.path]);

  // Redirect "/" → "/dashboard" from an effect, never during render
  // (a navigate() inside render races the hashchange subscription).
  useEffect(() => { if (route.path === "/") navigate("/dashboard"); }, [route.path]);
  const match = resolve(ROUTES, route.path === "/" ? "/dashboard" : route.path);
  const props = { user, health, version, onLogout, refreshMe, params: match?.params || {}, query: route.query };

  // On route change update the page title and move focus to the main
  // region so keyboard/screen-reader users land on the new content (A36).
  const current = route.path === "/" ? "/dashboard" : route.path;
  useEffect(() => {
    const top = "/" + current.split("/")[1];
    const key = LABEL_KEY_BY_PATH[current] || LABEL_KEY_BY_PATH[top];
    document.title = key ? `${t(key)} · Klopot` : t("shell.appTitle");
    // New page: start at the top and move focus to it for screen readers —
    // without the browser scrolling `main` into view, which on a phone pushed
    // the menu button off-screen.
    const main = document.getElementById("main-content");
    if (main) { main.focus({ preventScroll: true }); window.scrollTo(0, 0); }
  }, [current, lang]);

  const isActive = (p) => route.path === p || route.path.startsWith(p + "/");
  const [whatsNewOpen, setWhatsNewOpen] = useState(false);
  // Global search: Ctrl+K / ⌘K anywhere, or the search button.
  const [paletteOpen, setPaletteOpen] = useState(false);
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); setPaletteOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const pages = NAV.flatMap((g) => g.items).map((it) => ({ path: it.path, label: t(it.labelKey) }));
  const searchBtn = (where) => html`<button type="button" class=${"btn sm search-btn search-" + where} onClick=${() => setPaletteOpen(true)}
      aria-keyshortcuts="Control+K Meta+K">
      <span aria-hidden="true">⌕</span><span class="search-label">${t("palette.button")}</span><kbd>Ctrl K</kbd></button>`;

  // Language, theme, account and sign-out. In the top bar on wide screens; on a
  // phone the top bar is hidden and the same controls sit at the end of the menu.
  const prefs = (where) => html`<div class=${"prefs prefs-" + where}>
    <select class="small" value=${lang} onChange=${(e) => onLangChange(e.target.value)} aria-label=${t("lang.label")}>
      ${LANGS.map((l) => html`<option key=${l.id} value=${l.id}>${l.label}</option>`)}
    </select>
    <select class="small" value=${family} onChange=${(e) => setFamily(e.target.value)} aria-label=${t("theme.familyLabel")}>
      ${THEME_FAMILIES.map((f) => html`<option key=${f.id} value=${f.id}>${f.label}</option>`)}
    </select>
    <select class="small" value=${mode} onChange=${(e) => setMode(e.target.value)} aria-label=${t("theme.modeLabel")}>
      <option value="auto">${t("theme.auto")}</option><option value="light">${t("theme.light")}</option><option value="dark">${t("theme.dark")}</option>
    </select>
    <a href="#/account" class="small"><b>${user.username}</b></a>
    <button class="btn sm" onClick=${onLogout}>${t("common.signOut")}</button>
  </div>`;

  return html`<div class=${"shell" + (navOpen ? " nav-open" : "")}>
    <a class="skip-link" href="#main-content" onClick=${skipToMain}>${t("shell.skipToContent")}</a>
    <aside class="sidebar">
      <div class="brand"><${BrandIcon} /><${Wordmark} />
        ${health ? html`<span class=${"badge brand-health " + health.status} title=${t("shell.health")}>${statusLabel(health.status)}</span>` : null}
        ${searchBtn("phone")}
        <button class="nav-toggle" aria-expanded=${navOpen ? "true" : "false"}
                aria-controls="nav-menu" onClick=${() => setNavOpen((v) => !v)}>
          <span aria-hidden="true">${navOpen ? "✕" : "☰"}</span>
          <span class="sr-only">${navOpen ? t("shell.closeMenu") : t("shell.openMenu")}</span>
        </button>
      </div>
      <nav class="nav" id="nav-menu">
        ${NAV.map((g) => html`<div class="nav-group" key=${g.titleKey}>
          <div class="nav-title">${t(g.titleKey)}</div>
          ${g.items.map((it) => html`<a key=${it.path} href=${"#" + it.path}
              aria-current=${isActive(it.path) ? "page" : undefined}
              class=${isActive(it.path) ? "active" : ""}>
            ${t(it.labelKey)}${it.soon ? html`<span class="soon">${it.soon}</span>` : null}
          </a>`)}
        </div>`)}
        ${prefs("menu")}
      </nav>
      ${version ? html`<button class="ver-btn" onClick=${() => setWhatsNewOpen(true)}>
        <span class="ver mono">v${version}</span>
        <span class="ver-whats">${t("shell.whatsNew")}</span>
      </button>` : null}
    </aside>
    <div class="main">
      <header class="topbar">
        <span class="health">
          <span class="health-label muted small">${t("shell.health")}</span>
          ${health ? html`<a href="#/dashboard" class="badge ${health.status}"
              title=${Object.entries(health.components || {}).map(([k, c]) => `${componentLabel(k)}: ${statusLabel(c.status)}`).join("\n")}>
            ${statusLabel(health.status)}</a>` : html`<span class="badge">…</span>`}
        </span>
        <span class="spacer"></span>
        ${searchBtn("bar")}
        ${prefs("bar")}
      </header>
      <main class="content" id="main-content" tabindex="-1">
        ${match ? match.render(props) : html`<div class="card"><h1>${t("shell.notFoundTitle")}</h1><p class="muted">${t("shell.noScreenAt")} <code>${route.path}</code>.</p></div>`}
      </main>
    </div>
    <${CommandPalette} open=${paletteOpen} onClose=${() => setPaletteOpen(false)} pages=${pages} />
    <${Modal} open=${whatsNewOpen} title=${t("shell.whatsNew")} onClose=${() => setWhatsNewOpen(false)}>
      ${CHANGELOG.map((g) => html`<div class="cl-group" key=${g.version}>
        <div class="cl-ver mono">v${g.version}</div>
        <ul class="cl-list">${g.items.map((it, i) => html`<li key=${i}>${it}</li>`)}</ul>
      </div>`)}
    </${Modal}>
  </div>`;
}

// ── App (auth state) ─────────────────────────────────────────────
function App() {
  const [state, setState] = useState("booting"); // booting | boot-error | anon | must-change | ready
  const [bootError, setBootError] = useState(null); // non-401 failure of the initial /auth/me (UX-006)
  const [user, setUser] = useState(null);
  const [health, setHealth] = useState(null);
  const [version, setVersion] = useState(null);
  const [lang, setLangState] = useState(getLang);
  // Switch language: update the i18n runtime (which t() reads) and re-render
  // the tree so every string re-resolves live.
  const changeLang = useCallback((l) => { setLangState(setLang(l)); }, []);

  const refreshMe = useCallback(async () => {
    setBootError(null);
    try {
      const me = await api.me();
      setUser(me.user);
      setState(me.user.must_change_password ? "must-change" : "ready");
    } catch (e) {
      if (e.status === 401) { setUser(null); setState("anon"); }
      // A non-401 failure of the initial /auth/me used to leave the app stuck
      // on "Loading…". Surface it with a retry instead (UX-006).
      else { setBootError(e); setState("boot-error"); }
    }
  }, []);

  useEffect(() => { refreshMe(); }, [refreshMe]);

  // Health + version: /v1/health is public; poll every 30 s while signed in.
  useEffect(() => {
    let timer;
    const tick = async () => {
      try { const h = await api.health(); setHealth(h); setVersion(h.version); } catch { setHealth(null); }
      timer = setTimeout(tick, 30000);
    };
    tick();
    return () => clearTimeout(timer);
  }, []);

  // First screen after signing in: while the setup is incomplete (and not
  // hidden), an admin landing on the dashboard is taken to the setup guide —
  // once per browser session, so "Dashboard" in the menu still works.
  useEffect(() => {
    if (state !== "ready" || user?.role !== "admin") return;
    let seen = false;
    try { seen = sessionStorage.getItem("alertd.setupShown") === "1"; sessionStorage.setItem("alertd.setupShown", "1"); } catch { /* private mode */ }
    if (seen) return;
    const path = (location.hash || "#/").slice(1).split("?")[0];
    if (path !== "/" && path !== "/dashboard" && path !== "") return;
    api.get("/v1/setup/status").then((s) => { if (!s.complete && !s.dismissed) navigate("/setup", undefined, { replace: true }); }).catch(() => {});
  }, [state, user]);

  useEffect(() => {
    const offExpired = onApiEvent("auth:expired", () => {
      setUser((u) => { if (u) toast.info(t("shell.sessionEnded")); return null; });
      setState("anon");
    });
    const offMust = onApiEvent("auth:must-change", () => setState("must-change"));
    return () => { offExpired(); offMust(); };
  }, []);

  async function logout() {
    try { await api.logout(); } catch { /* already gone */ }
    setUser(null); setState("anon"); navigate("/dashboard");
  }

  let screen;
  if (state === "booting") screen = html`<div class="auth-wrap"><p class="muted">${t("common.loading")}</p></div>`;
  else if (state === "boot-error") screen = html`<div class="auth-wrap"><${ErrorState} error=${bootError} label=${t("shell.bootError")} onRetry=${() => { setState("booting"); refreshMe(); }} /></div>`;
  else if (state === "anon") screen = html`<${LoginView} version=${version} onLoggedIn=${(u) => { setUser(u); setState(u.must_change_password ? "must-change" : "ready"); }} />`;
  else if (state === "must-change") screen = html`<${ChangePasswordView} user=${user} onChanged=${refreshMe} onLogout=${logout} />`;
  else screen = html`<${Shell} user=${user} health=${health} version=${version} onLogout=${logout} refreshMe=${refreshMe} lang=${lang} onLangChange=${changeLang} />`;

  return html`${screen}<${Toasts} />`;
}

setLang(getLang());
applyTheme(readFamily(), readMode());
render(html`<${App} />`, document.getElementById("app"));
// Phone: list tables become one card per row (lib/stack_tables.js).
stackTables(document.getElementById("app"));
