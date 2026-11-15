// Boot smoke: evaluate the real app.js module end-to-end in jsdom and assert it
// renders without throwing. Guards the whole import graph + the top-level boot
// calls (applyTheme/render) that unit tests on individual libs never exercise —
// a renamed-but-still-referenced helper at module scope blanks the admin UI,
// and node --check only catches syntax, not undefined references.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, flush } from "./support/dom.mjs";

await setupDom();

// The shell polls /v1/health every 30s via setTimeout; neutralise long timers
// so the test process can exit, leaving short timers (flush) working.
const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms, ...rest) => (ms >= 10000 ? 0 : realSetTimeout(fn, ms, ...rest));

test("admin shell module boots and renders without throwing", async () => {
  try {
    // Importing runs app.js top-to-bottom: the import graph, the top-level
    // applyTheme(...) FOUC call, and render(<App/>). Any throw fails here.
    await import("../../app/admin_ui/static/app.js");
    await flush(60);
    const app = document.getElementById("app");
    assert.ok(app && app.childNodes.length > 0, "app.js rendered content into #app");
  } finally {
    globalThis.setTimeout = realSetTimeout;
  }
});
