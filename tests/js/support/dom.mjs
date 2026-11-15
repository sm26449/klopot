// jsdom + axe-core harness for the admin-UI accessibility sweep (audit V13).
//
// Renders the real vendored-preact views/components into a jsdom document with
// network + websocket stubbed to empty-but-valid data, then runs axe-core and
// returns only the accessible-NAME violations (a control a screen reader can't
// identify). Not a *.test.mjs file, so `node --test tests/js/*.mjs` ignores it.
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const META = JSON.parse(readFileSync(
  fileURLToPath(new URL("./meta_kinds.fixture.json", import.meta.url)), "utf8"));

let _render, _html;

function fakeResponse(bodyObj, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => bodyObj,
    text: async () => JSON.stringify(bodyObj),
  };
}

function routeData(pathname) {
  if (pathname.endsWith("/v1/meta/kinds")) return META;
  if (pathname.endsWith("/v1/schedules/preview")) return { next: [], tz: "UTC" };
  if (/\/v1\/(templates|channels|inputs|variables|rules|schedules|snooze|snoozes|audit|api_keys|log|incidents)$/.test(pathname))
    return { items: [], total: 0, offset: 0, limit: 50 };
  if (pathname.endsWith("/v1/state")) return { variables: [], cache_size: 0, last_mqtt_ts: null };
  if (pathname.endsWith("/v1/health")) return { status: "ok" };
  if (pathname.endsWith("/v1/dashboard")) return {};
  return {};
}

export async function setupDom() {
  const dom = new JSDOM("<!doctype html><html><body><div id='app'></div></body></html>",
    { url: "http://testserver", pretendToBeVisual: true });
  const w = dom.window;
  for (const k of [
    "window", "document", "navigator", "HTMLElement", "Node", "Event", "CustomEvent",
    "MouseEvent", "KeyboardEvent", "getComputedStyle", "requestAnimationFrame",
    "cancelAnimationFrame", "MutationObserver", "localStorage", "sessionStorage", "location",
  ]) {
    // defineProperty, not assignment: since Node 21 `navigator` is a
    // getter-only global and `globalThis.navigator = …` throws.
    Object.defineProperty(globalThis, k, { value: w[k], configurable: true, writable: true });
  }
  globalThis.window = w;
  globalThis.document = w.document;
  globalThis.fetch = async (url) => fakeResponse(routeData(new URL(url, "http://testserver").pathname));
  w.fetch = globalThis.fetch;
  globalThis.WebSocket = class { constructor() {} close() {} send() {} addEventListener() {} removeEventListener() {} };
  w.WebSocket = globalThis.WebSocket;

  const h = await import("../../../app/admin_ui/static/lib/h.js");
  _html = h.html;
  _render = h.render;
  return { html: _html, render: _render };
}

export function mount(vnode) {
  const app = document.getElementById("app");
  _render(vnode, app);
  return app;
}

export function unmount() {
  _render(null, document.getElementById("app"));
}

export function flush(ms = 400) {
  return new Promise((r) => setTimeout(r, ms));
}

// Accessible-name rules: a control a screen reader can't name.
const NAME_RULES = [
  "label", "select-name", "aria-input-field-name",
  "aria-toggle-field-name", "frame-title", "input-button-name",
  "button-name", "link-name",
];

export async function nameViolations(rootSelector = "#app") {
  const axe = (await import("axe-core")).default;
  const root = document.querySelector(rootSelector);
  const res = await axe.run(root, { runOnly: { type: "rule", values: NAME_RULES } });
  return res.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.html) }));
}
