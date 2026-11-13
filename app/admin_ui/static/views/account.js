import { html, useEffect, useState } from "../lib/h.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { ErrorState } from "../lib/ui.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import { PasswordForm } from "./password.js";
import { t } from "../lib/i18n.js";

export function AccountView({ user, onLogout, refreshMe, health }) {
  const [sessions, setSessions] = useState(null);
  const [settings, setSettings] = useState(null);
  const [busy, setBusy] = useState(false);
  const [errSessions, setErrSessions] = useState(null); // UX-006
  const [errSettings, setErrSettings] = useState(null);

  async function load() {
    setErrSessions(null);
    try { setSessions(await api.sessions()); } catch (e) { setErrSessions(e); }
  }
  function loadSettings() {
    setErrSettings(null);
    api.get("/v1/settings").then((r) => setSettings(r.items)).catch(setErrSettings);
  }
  useEffect(() => { load(); }, []);
  useEffect(() => { loadSettings(); }, []);

  async function revoke(id) {
    if (!confirm(t("account.confirmRevoke"))) return;
    setBusy(true);
    try { await api.revokeSession(id); toast.ok(t("account.toastRevoked")); await load(); }
    catch (e) { toast.error(e); } finally { setBusy(false); }
  }
  async function revokeOthers() {
    if (!confirm(t("account.confirmRevokeOthers"))) return;
    setBusy(true);
    try { const r = await api.revokeOtherSessions(); toast.ok(t("account.toastRevokedN", { n: r.revoked })); await load(); }
    catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  return html`<div>
    <div class="page-head">
      <div><h1>${t("account.title")}</h1><p class="muted">${t("account.signedInAs")} <b>${user.username}</b> ${t("account.roleParen", { role: user.role })}</p></div>
      <div class="actions"><button class="btn" onClick=${onLogout}>${t("account.signOut")}</button></div>
    </div>
    <div class="grid">
      <div class="card">
        <h2>${t("account.changePassword")}</h2>
        <${PasswordForm} username=${user.username} onChanged=${() => { refreshMe(); load(); }} />
      </div>
      <div class="card">
        <h2>${t("account.details")}</h2>
        <dl class="kv">
          <dt>${t("account.lastLogin")}</dt><dd>${fmtDateTime(user.last_login_at)}</dd>
          <dt>${t("account.passwordChanged")}</dt><dd>${fmtDateTime(user.password_changed_at)}</dd>
          <dt>${t("account.mustChange")}</dt><dd>${user.must_change_password ? t("account.yes") : t("account.no")}</dd>
        </dl>
      </div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>${t("account.effectiveSettings")} <span class="muted small">${t("account.effectiveSettingsNote")}</span></h2>
      ${errSettings && settings === null ? html`<${ErrorState} error=${errSettings} onRetry=${loadSettings} />` : settings === null ? html`<p class="muted">${t("account.loading")}</p>` : html`<table class="tbl"><tbody>
        ${settings.map((s) => html`<tr key=${s.key}>
          <td class="mono small">${s.key}</td>
          <td class="mono">${s.value === null ? "—" : typeof s.value === "boolean" ? String(s.value) : s.value}</td>
          <td><span class="badge plain small">${s.source}</span></td>
        </tr>`)}</tbody></table>
        <p class="muted small" style="margin-top:8px">${t("account.envNote")}${health?.docs_enabled ? html` <a href="/docs" target="_blank" rel="noopener">${t("account.openApiLink")}</a>` : ""}</p>`}
    </div>

    <div class="card" style="margin-top:14px">
      <div class="page-head" style="margin-bottom:8px">
        <h2 style="margin:0">${t("account.activeSessions")}</h2>
        <div class="actions">
          <button class="btn sm" onClick=${load} disabled=${busy}>${t("account.refresh")}</button>
          <button class="btn sm danger" onClick=${revokeOthers} disabled=${busy || !sessions || sessions.length < 2}>${t("account.signOutOthers")}</button>
        </div>
      </div>
      ${errSessions && sessions === null ? html`<${ErrorState} error=${errSessions} onRetry=${load} />` : sessions === null ? html`<p class="muted">${t("account.loading")}</p>` : html`<table class="tbl sessions">
        <thead><tr><th>${t("account.colSession")}</th><th>${t("account.colIp")}</th><th>${t("account.colBrowser")}</th><th>${t("account.colStarted")}</th><th>${t("account.colLastSeen")}</th><th>${t("account.colExpires")}</th><th></th></tr></thead>
        <tbody>${sessions.map((s) => html`<tr key=${s.id}>
          <td>${s.current ? html`<span class="badge ok plain">${t("account.thisBrowser")}</span>` : html`<span class="mono">#${s.id}</span>`}</td>
          <td class="mono">${s.ip || "—"}</td>
          <td class="small muted" title=${s.user_agent || ""}>${(s.user_agent || "—").slice(0, 60)}</td>
          <td>${fmtDateTime(s.created_at)}</td>
          <td title=${fmtDateTime(s.last_seen_at)}>${fmtRelative(s.last_seen_at)}</td>
          <td title=${fmtDateTime(s.expires_at)}>${fmtRelative(s.expires_at)}</td>
          <td>${s.current ? null : html`<button class="btn sm danger" onClick=${() => revoke(s.id)} disabled=${busy}>${t("account.revoke")}</button>`}</td>
        </tr>`)}</tbody>
      </table>`}
    </div>
  </div>`;
}
