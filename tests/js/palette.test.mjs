// Global search ranking (lib/palette.js matchScore).
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { matchScore, CommandPalette } = await import("../../app/admin_ui/static/lib/palette.js");

test("a substring beats letters in order, which beat no match", () => {
  assert.ok(matchScore("disk_full", "disk") > matchScore("dash_info_sk", "disk"));
  assert.ok(matchScore("dash_info_sk", "disk") > 0, "d…i…s…k in order still matches");
  assert.equal(matchScore("rules", "zz"), 0);
});

test("an earlier and tighter match ranks higher; empty query matches everything", () => {
  assert.ok(matchScore("rules", "rul") > matchScore("all rules", "rul"));
  assert.ok(matchScore("rules", "rules") > matchScore("rules_extra", "rules"));
  assert.equal(matchScore("anything", "  "), 1);
});


test("items that arrive after typing do not move the highlight; Enter opens what was highlighted", async () => {
  // CI caught it: "Channels" was highlighted, the items landed and re-sorted
  // the list, and Enter opened whatever had moved to the first position.
  let release;
  const gate = new Promise((r) => { release = r; });
  const page = (body) => ({ ok: true, status: 200, headers: { get: () => "application/json" },
    json: async () => body, text: async () => JSON.stringify(body) });
  globalThis.fetch = async (url) => {
    const path = new URL(String(url), "http://testserver").pathname;
    await gate;
    if (path.endsWith("/v1/channels")) return page({ items: [{ id: 1, name: "chanels", kind: "webhook" }], total: 1 });
    return page({ items: [], total: 0 });
  };
  location.hash = "#/rules";
  mount(html`<${CommandPalette} open=${true} onClose=${() => {}} pages=${[{ label: "Channels", path: "/channels" }, { label: "Rules", path: "/rules" }]} />`);
  await flush(50);
  const input = document.querySelector(".palette-input");
  input.value = "chan";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  await flush(50);
  const highlighted = () => document.querySelector('.palette [role=option][aria-selected="true"] .palette-label')?.textContent;
  assert.equal(highlighted(), "Channels");
  release();                                   // the channel "chanels" (a better match) arrives now
  await flush(100);
  assert.ok([...document.querySelectorAll(".palette-label")].some((n) => n.textContent === "chanels"), "the item arrived");
  assert.equal(highlighted(), "Channels", "the highlight stayed on what the operator saw");
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await flush(50);
  assert.equal(location.hash, "#/channels");
  unmount();
});
