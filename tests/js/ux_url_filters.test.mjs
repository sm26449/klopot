// UX-015: Rules/Audit filters didn't track the URL, so they were lost on reload
// and ignored on a deep-link. useUrlFilters initialises from the URL query,
// writes changes back (replace), and a view reads its filters from the URL.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { useUrlFilters } = await import("../../app/admin_ui/static/lib/router.js");
const { useState } = await import("../../app/admin_ui/static/lib/h.js");

test("useUrlFilters initialises from the URL and writes changes back", async () => {
  let setF, now;
  function Probe({ query }) {
    const [f, sf] = useUrlFilters("/x", query, { a: "", b: "" });
    setF = sf; now = f;
    return html`<span>${f.a}</span>`;
  }
  mount(html`<${Probe} query=${{ a: "1" }} />`);
  await flush(10);
  assert.equal(now.a, "1", "initialised from the URL query");
  assert.equal(now.b, "", "missing keys default");

  setF("a", "2");
  await flush(10);
  assert.equal(now.a, "2", "filter state updated");
  assert.match(window.location.hash, /a=2/, "the change is written to the URL");
  unmount();
});

function okJson(body) {
  return { ok: true, status: 200,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body, text: async () => JSON.stringify(body) };
}

// ── R5: the page offset also rides the URL (survives reload) ──
test("offset initialises from ?skip and setOffset writes it back", async () => {
  let api, off;
  function Probe({ query }) {
    const [, , , offset, setOffset] = useUrlFilters("/x", query, { a: "" });
    api = { setOffset }; off = offset;
    return html`<span>${offset}</span>`;
  }
  mount(html`<${Probe} query=${{ skip: "50" }} />`);
  await flush(10);
  assert.equal(off, 50, "offset read from ?skip");

  api.setOffset(100);
  await flush(10);
  assert.equal(off, 100, "offset state updated");
  assert.match(window.location.hash, /skip=100/, "the page is written to the URL (survives reload)");
  unmount();
});

// ── R5: any filter change resets to page 1 and drops ?skip ──
test("a filter change resets the offset and removes ?skip", async () => {
  let api, off;
  function Probe({ query }) {
    const [, setFilter, , offset] = useUrlFilters("/x", query, { a: "" });
    api = { setFilter }; off = offset;
    return html`<span>${offset}</span>`;
  }
  mount(html`<${Probe} query=${{ a: "x", skip: "50" }} />`);
  await flush(10);
  assert.equal(off, 50, "started on page 2");
  api.setFilter("a", "y");
  await flush(10);
  assert.equal(off, 0, "filter change reset to page 1");
  assert.equal(/skip=/.test(window.location.hash), false, "?skip dropped from the URL");
  unmount();
});

// ── R5 (gap 3): an external query without ?skip lands on page 1, not the
// stale offset. The resync is driven by the query prop changing. ──
test("an external query change without ?skip resyncs the offset to 0", async () => {
  let setQuery, off;
  function Harness() {
    const [q, setQ] = useState({ skip: "50" });
    setQuery = setQ;
    const [, , , offset] = useUrlFilters("/x", q, { enabled: "" });
    off = offset;
    return html`<span>${offset}</span>`;
  }
  mount(html`<${Harness} />`);
  await flush(10);
  assert.equal(off, 50, "on page 2 initially");

  setQuery({ enabled: "true" }); // external nav: #/x?enabled=true (no skip)
  await flush(20);
  assert.equal(off, 0, "the stale offset was reset — no skip=50 leaking onto the new filter");
  unmount();
});

// ── R5 (gap 2): the Log writes its filters to the URL ──
test("Log writes a filter change to the URL", async () => {
  globalThis.fetch = async () => okJson({ items: [], total: 0 });
  globalThis.window.fetch = globalThis.fetch;
  window.location.hash = "#/log";

  const m = await import("../../app/admin_ui/static/views/log.js");
  mount(html`<${m.LogView} query=${{}} />`);
  await flush(60);

  const box = [...document.querySelectorAll("input")].find((i) => /search/i.test(i.getAttribute("aria-label") || i.placeholder || ""));
  assert.ok(box, "a search input is present");
  box.value = "grid";
  box.dispatchEvent(new window.Event("input", { bubbles: true }));
  await flush(20);
  assert.match(window.location.hash, /search=grid/, "the Log filter is written to the URL");
  unmount();
});

test("Rules reads its filters from the URL (deep-link / reload)", async () => {
  const urls = [];
  globalThis.fetch = async (url) => { urls.push(String(url)); return okJson({ items: [], total: 0 }); };
  globalThis.window.fetch = globalThis.fetch;

  const m = await import("../../app/admin_ui/static/views/rules.js");
  mount(html`<${m.RulesView} query=${{ enabled: "true" }} />`);
  await flush(60);

  const listReq = urls.find((u) => u.includes("/v1/rules?") && u.includes("enabled=true"));
  assert.ok(listReq, `the list was queried with the URL filter: ${urls.filter((u) => u.includes("/v1/rules")).join(" | ")}`);
  unmount();
});
