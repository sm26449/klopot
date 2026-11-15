import { html } from "../lib/h.js";

// Stand-in for screens that land in later phases (F4–F7). Keeps the
// navigation complete so the shell can be reviewed as a whole.
export function PlaceholderView({ title, phase, blurb, api: endpoint }) {
  return html`<div>
    <div class="page-head"><div><h1>${title}</h1><p class="muted">${blurb}</p></div></div>
    <div class="card">
      <p>This screen arrives in <b>phase ${phase}</b> of the admin-UI plan.</p>
      ${endpoint ? html`<p class="muted small">Until then the data is available on the API: <code>${endpoint}</code> (<a href="#/api">API</a>).</p>` : null}
    </div>
  </div>`;
}
