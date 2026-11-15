// UX-007 / R2: a dirty editor must survive an in-app navigation (sidebar link,
// back/forward, programmatic navigate) — not just Esc/overlay/X. A registered
// nav guard that declines blocks the navigation and the view/route does NOT
// change, so the component (and its draft) stay mounted.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { useRoute, addNavGuard, navigate } = await import("../../app/admin_ui/static/lib/router.js");

test("navigate() is blocked by a declining guard, allowed when none", () => {
  window.location.hash = "#/rules";
  const off = addNavGuard(() => false); // always veto
  navigate("/log");
  assert.equal(window.location.hash, "#/rules", "navigate was vetoed");
  off();
  navigate("/log");
  assert.equal(window.location.hash, "#/log", "navigate works once the guard is gone");
});

test("useRoute vetoes a direct hash change and keeps the current route", async () => {
  window.location.hash = "#/rules";
  let routeNow;
  function Probe() { const r = useRoute(); routeNow = r.path; return html`<span>${r.path}</span>`; }
  // Preact installs useEffect subscriptions after an animation frame. The
  // first render's path does not prove the hash listener is ready; 20 ms
  // raced that subscription under the full suite's CPU load.
  let subscribed = false;
  const originalAdd = window.addEventListener;
  window.addEventListener = function (type, ...args) {
    originalAdd.call(this, type, ...args);
    if (type === "hashchange") subscribed = true;
  };
  try {
    mount(html`<${Probe} />`);
    for (let n = 0; !subscribed && n < 100; n++) await flush(10);
    assert.ok(subscribed, "router effect subscribed before navigating");
  } finally { window.addEventListener = originalAdd; }
  assert.equal(routeNow, "/rules", "started on /rules");

  const off = addNavGuard(() => false); // simulate a dirty editor declining
  window.location.hash = "#/log";       // a sidebar link / back-forward
  await flush(40);
  assert.equal(routeNow, "/rules", "the view did NOT switch — draft preserved");
  assert.equal(window.location.hash, "#/rules", "the hash was reverted");

  off();
  window.location.hash = "#/log";
  await flush(40);
  assert.equal(routeNow, "/log", "navigation proceeds once there is no guard");
  unmount();
});
