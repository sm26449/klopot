import { html, useState } from "../lib/h.js";
import { api } from "../lib/api.js";
import { toast } from "../lib/toast.js";
import { t } from "../lib/i18n.js";

const MIN = 12;

// Shared by the forced-change screen and the Account page.
export function PasswordForm({ username, onChanged, submitLabel = t("password.changePassword") }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const problems = [];
  if (next && next.length < MIN) problems.push(t("password.minChars", { n: MIN }));
  if (next && username && next.toLowerCase() === username.toLowerCase()) problems.push(t("password.mustDifferUsername"));
  if (next && current && next === current) problems.push(t("password.mustDifferCurrent"));
  if (confirm && confirm !== next) problems.push(t("password.confirmMismatch"));
  const ready = current && next && confirm && problems.length === 0;

  async function submit(ev) {
    ev.preventDefault();
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.changePassword(current, next);
      setCurrent(""); setNext(""); setConfirm("");
      toast.ok(t("password.toastChanged"));
      onChanged && onChanged();
    } catch (e) {
      if (e.status === 401) setError(t("password.currentIncorrect"));
      else if (e.code === "PASSWORD_POLICY") setError(e.message);
      else setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return html`<form onSubmit=${submit} autocomplete="on">
    <div class="field">
      <label for="cur">${t("password.currentLabel")}</label>
      <input id="cur" type="password" autocomplete="current-password" value=${current}
        onInput=${(e) => setCurrent(e.target.value)} required />
    </div>
    <div class="field">
      <label for="new">${t("password.newLabel")}</label>
      <input id="new" type="password" autocomplete="new-password" value=${next} minlength=${MIN}
        onInput=${(e) => setNext(e.target.value)} required />
      <span class="hint">${t("password.hint", { n: MIN })}</span>
    </div>
    <div class="field">
      <label for="cfm">${t("password.confirmLabel")}</label>
      <input id="cfm" type="password" autocomplete="new-password" value=${confirm}
        onInput=${(e) => setConfirm(e.target.value)} required
        aria-invalid=${confirm && confirm !== next ? "true" : "false"} />
    </div>
    ${problems.length ? html`<p class="error">${problems.join("; ")}</p>` : null}
    ${error ? html`<p class="error" role="alert">${error}</p>` : null}
    <div class="form-actions">
      <button class="btn primary" type="submit" disabled=${!ready || busy}>${busy ? t("password.saving") : submitLabel}</button>
    </div>
  </form>`;
}

export function ChangePasswordView({ user, onChanged, onLogout }) {
  return html`<div class="auth-wrap">
    <div class="card auth-card">
      <div class="brand"><img src="./favicon.svg" alt="" /><b>${t("password.setNewPassword")}</b></div>
      <p class="muted small">${t("password.signedInAs")} <b>${user.username}</b> ${t("password.bootstrapNote")}</p>
      <${PasswordForm} username=${user.username} onChanged=${onChanged} submitLabel=${t("password.saveAndContinue")} />
      <div class="form-actions" style="margin-top:14px">
        <button class="btn ghost sm" type="button" onClick=${onLogout}>${t("password.signOut")}</button>
      </div>
    </div>
  </div>`;
}
