// UX-013: the LiveStatus indicator maps the real WS status to a severity dot +
// a localized, politely-announced label (ADR-0001: stream health uses severity
// colours + text, never the amber "live" dot).
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { LiveStatus } = await import("../../app/admin_ui/static/lib/ui.js");

const cases = [
  ["open", "ok", /live/i],
  ["reconnecting", "warn", /reconnect/i],
  ["auth-ended", "crit", /disconnect/i],
];

for (const [status, cls, label] of cases) {
  test(`status "${status}" → .dot.${cls} + announced label`, async () => {
    mount(html`<${LiveStatus} status=${status} />`);
    await flush(10);
    const dot = document.querySelector(".live-status .dot");
    assert.ok(dot, "a dot is rendered");
    assert.ok(dot.classList.contains(cls), `dot should carry severity class ${cls}`);
    const live = document.querySelector('[aria-live="polite"]');
    assert.ok(live, "the label is a polite live region");
    assert.match(live.textContent, label);
    unmount();
  });
}
