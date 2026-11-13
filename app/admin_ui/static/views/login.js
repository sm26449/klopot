import { html, useEffect, useState } from "../lib/h.js";
import { api } from "../lib/api.js";
import { fmtSeconds } from "../lib/format.js";
import { t } from "../lib/i18n.js";

export function LoginView({ onLoggedIn, version }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [lockedFor, setLockedFor] = useState(0);

  useEffect(() => {
    if (lockedFor <= 0) return;
    const t = setTimeout(() => setLockedFor((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [lockedFor]);

  async function submit(ev) {
    ev.preventDefault();
    if (busy || lockedFor > 0) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(username.trim(), password);
      setPassword("");
      onLoggedIn(res.user);
    } catch (e) {
      if (e.status === 423) {
        const secs = e.detail?.retry_after_sec ?? 60;
        setLockedFor(secs);
        setError(t("login.tooManyAttempts"));
      } else if (e.status === 401) {
        setError(t("login.invalidCredentials"));
      } else {
        setError(e.message);
      }
    } finally {
      setBusy(false);
    }
  }

  return html`<div class="auth-wrap">
    <form class="card auth-card" onSubmit=${submit} autocomplete="on">
      <div class="brand"><img src="./favicon.svg" alt="" /><b>${t("login.brandTitle")}</b>
        ${version ? html`<span class="ver muted small">v${version}</span>` : null}</div>
      <div class="field">
        <label for="u">${t("login.usernameLabel")}</label>
        <input id="u" name="username" autocomplete="username" value=${username}
          onInput=${(e) => setUsername(e.target.value)} required autofocus />
      </div>
      <div class="field">
        <label for="p">${t("login.passwordLabel")}</label>
        <input id="p" name="password" type="password" autocomplete="current-password" value=${password}
          onInput=${(e) => setPassword(e.target.value)} required aria-invalid=${error ? "true" : "false"} />
      </div>
      ${error ? html`<p class="error" role="alert">${error}
        ${lockedFor > 0 ? html` ${t("login.tryAgainIn")} <b>${fmtSeconds(lockedFor)}</b>.` : null}</p>` : null}
      <div class="form-actions">
        <button class="btn primary" type="submit" disabled=${busy || lockedFor > 0}>
          ${busy ? t("login.signingIn") : t("login.signIn")}
        </button>
      </div>
    </form>
  </div>`;
}
