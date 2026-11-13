// UX-006 / R1: error/retry must extend BEYOND the first load. A failed *refresh*
// after a first success used to silently keep stale rows looking current; now
// the last-good data stays visible under a StaleBanner with a retry, while a
// failed first load still gets the full-replacement ErrorState. The same proof
// must pass both before and after the first success.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { useLoader } = await import("../../app/admin_ui/static/lib/loader.js");
const { StaleBanner, ErrorState } = await import("../../app/admin_ui/static/lib/ui.js");
const { useState } = await import("../../app/admin_ui/static/lib/h.js");

const src = (p) => readFileSync(fileURLToPath(new URL("../../app/admin_ui/static/views/" + p, import.meta.url)), "utf8");

// ── Mechanism: a failed reload keeps the last-good data AND reports the error ──
test("useLoader retains data on a failed refresh and clears the error on recovery", async () => {
  let n = 0;
  // ok → fail → ok
  const fetcher = async () => {
    n++;
    if (n === 2) throw new Error("boom");
    return { rows: n };
  };
  let api;
  function Probe() {
    const [data, , reload, error] = useLoader(fetcher, []);
    api = { reload };
    // Mirror the view contract exactly.
    return html`<div>
      ${error && data ? html`<${StaleBanner} error=${error} onRetry=${reload} />` : null}
      ${error && !data ? html`<${ErrorState} error=${error} onRetry=${reload} />` : null}
      ${data ? html`<span class="rows">${data.rows}</span>` : html`<span class="loading">…</span>`}
    </div>`;
  }
  mount(html`<${Probe} />`);
  await flush(40);
  assert.equal(document.querySelector(".rows").textContent, "1", "first load shows data");
  assert.equal(document.querySelector(".stale-banner"), null, "no stale banner on a clean load");

  api.reload();                       // second call throws
  await flush(40);
  assert.ok(document.querySelector(".stale-banner"), "failed refresh shows the stale banner");
  assert.equal(document.querySelector(".error-state"), null, "not the full-replacement error — data is kept");
  assert.equal(document.querySelector(".rows").textContent, "1", "the last-good rows are still shown");

  api.reload();                       // third call ok
  await flush(40);
  assert.equal(document.querySelector(".stale-banner"), null, "banner clears once the refresh succeeds");
  assert.equal(document.querySelector(".rows").textContent, "3", "data updated to the fresh result");
  unmount();
});

// ── Render: StaleBanner is a polite retry strip with a swappable label ──
test("StaleBanner shows the refresh message + retry, and honours a custom label", async () => {
  let retried = 0;
  mount(html`<${StaleBanner} error=${{ message: "x" }} onRetry=${() => retried++} />`);
  await flush(10);
  let box = document.querySelector(".stale-banner");
  assert.equal(box.getAttribute("role"), "alert");
  assert.match(box.textContent, /refresh|reîmprospăt/i);
  const btn = box.querySelector("button");
  assert.match(btn.textContent, /retry|reîncear/i);
  btn.click();
  assert.equal(retried, 1, "retry fires the handler");
  unmount();

  mount(html`<${StaleBanner} error=${null} label="Custom detail error" />`);
  await flush(10);
  assert.match(document.querySelector(".stale-banner").textContent, /Custom detail error/);
  assert.equal(document.querySelector(".stale-banner button"), null, "no retry button without onRetry");
  unmount();
});

// ── Contract: every list view wires the stale case and keeps ErrorState ──
test("all list views render StaleBanner for a kept-data error and ErrorState for the empty case", () => {
  const cases = [
    ["rules.js", "data"], ["log.js", "data"], ["audit.js", "data"],
    ["templates.js", "all"], ["variables.js", "items"], ["schedules.js", "items"],
    ["channels.js", "channels"], ["inputs.js", "items"], ["apikeys.js", "items"],
  ];
  for (const [file, dataVar] of cases) {
    const s = src(file);
    const errVar = /channels|inputs|apikeys/.test(file) ? "err" : "error";
    assert.match(s, /\$\{StaleBanner\}/, `${file} imports/uses StaleBanner`);
    // stale: error && <data> ... StaleBanner
    assert.ok(
      new RegExp(`${errVar}\\s*&&\\s*${dataVar}\\b[^]*?StaleBanner`).test(s),
      `${file} shows StaleBanner when ${errVar} && ${dataVar}`,
    );
    // empty-error path still present (full-replacement ErrorState)
    assert.match(s, /\$\{ErrorState\}/, `${file} keeps ErrorState for the empty-error case`);
  }
});

// ── Contract: the Log detail drawer surfaces a failed detail load with retry ──
test("the Log detail drawer tracks a detail error and offers retry", () => {
  const s = src("log.js");
  assert.match(s, /setDetailErr/, "detail load error is captured (not swallowed)");
  assert.match(s, /detailErr\s*\?[^]*?StaleBanner[^]*?detailError/, "a detail-error banner is shown");
  assert.match(s, /setRetry\(\(n\)\s*=>\s*n\s*\+\s*1\)/, "retry re-runs the detail load");
  assert.match(s, /\[row,\s*retry\]/, "the detail effect depends on the retry nonce");
});
