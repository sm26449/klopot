// UX-007: a session that expires mid-edit unmounts the whole shell, so the
// Drawer's dirty-close guards never fire and the draft is lost. useDraft stashes
// a dirty draft in sessionStorage keyed by editor + id; on reopen the editor
// offers to restore or discard it. This covers the hook's persist / recover /
// restore / clear behaviour, plus the DraftBanner and the UX-017 primitives
// (Pager "of", ListMeta "item(s)") that were the last hard-coded English.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom, mount, unmount, flush } from "./support/dom.mjs";

const { html } = await setupDom();
const { useDraft, draftKey } = await import("../../app/admin_ui/static/lib/draft.js");
const { DraftBanner, Pager, ListMeta } = await import("../../app/admin_ui/static/lib/ui.js");
const { setLang } = await import("../../app/admin_ui/static/lib/i18n.js");

// Preact flushes effects on the next animation frame (jsdom's pretendToBeVisual
// raf, ~16ms), so a draft write lands only after a frame — settle well past it.
const settle = () => flush(80);

// Capture the live hook result from inside a mounted component. A unique `key`
// per mount forces a fresh instance (and fresh hook state) every time.
let ref;
let seq = 0;
function Probe({ view, id, value, dirty }) {
  ref = useDraft(view, id, value, dirty);
  return html`<i />`;
}
async function mountProbe(props) {
  mount(html`<${Probe} key=${++seq} ...${props} />`);
  await settle();
}
async function reset() {
  unmount();
  await settle();            // drain any effects the prior test scheduled
  sessionStorage.clear();
}

test("a dirty draft is persisted under alertd.draft.<view>.<id>", async () => {
  await reset();
  await mountProbe({ view: "rules", id: 5, value: { name: "x", n: 2 }, dirty: true });
  assert.equal(sessionStorage.getItem(draftKey("rules", 5)), JSON.stringify({ name: "x", n: 2 }));
});

test("a clean editor persists nothing", async () => {
  await reset();
  await mountProbe({ view: "rules", id: 5, value: { name: "x" }, dirty: false });
  assert.equal(sessionStorage.getItem(draftKey("rules", 5)), null);
});

test("a stored draft is recovered on a fresh mount; none → null", async () => {
  await reset();
  sessionStorage.setItem(draftKey("rules", 7), JSON.stringify({ name: "recovered", n: 9 }));
  await mountProbe({ view: "rules", id: 7, value: { name: "", n: 0 }, dirty: false });
  assert.deepEqual(ref.recovered, { name: "recovered", n: 9 }, "recovers the stored draft");

  await reset();
  await mountProbe({ view: "rules", id: 99, value: { name: "" }, dirty: false });
  assert.equal(ref.recovered, null, "no stored draft → recovered is null");
});

test("a new-editor draft keys on the literal 'new' slot", async () => {
  await reset();
  await mountProbe({ view: "channels", id: null, value: { name: "draft" }, dirty: true });
  assert.equal(sessionStorage.getItem("alertd.draft.channels.new"), JSON.stringify({ name: "draft" }));
});

test("restore() hides the banner", async () => {
  await reset();
  sessionStorage.setItem(draftKey("rules", 3), JSON.stringify({ name: "old" }));
  await mountProbe({ view: "rules", id: 3, value: { name: "old" }, dirty: false });
  assert.deepEqual(ref.recovered, { name: "old" });
  ref.restore();
  await settle();
  assert.equal(ref.recovered, null, "banner is dismissed after restore");
});

test("clear() removes the stored draft and stops it being rewritten while dirty", async () => {
  await reset();
  await mountProbe({ view: "rules", id: 5, value: { name: "typed" }, dirty: true });
  assert.ok(sessionStorage.getItem(draftKey("rules", 5)), "persisted while dirty");
  ref.clear();
  await settle();
  // Even though `dirty` is still true, clear() must win — a save-time re-render
  // may not rewrite the slot we just cleared.
  assert.equal(sessionStorage.getItem(draftKey("rules", 5)), null, "cleared and stays cleared");
});

test("dismiss() drops the stored draft and hides the banner", async () => {
  await reset();
  sessionStorage.setItem(draftKey("rules", 8), JSON.stringify({ name: "unwanted" }));
  await mountProbe({ view: "rules", id: 8, value: { name: "" }, dirty: false });
  assert.deepEqual(ref.recovered, { name: "unwanted" });
  ref.dismiss();
  await settle();
  assert.equal(ref.recovered, null, "banner gone");
  assert.equal(sessionStorage.getItem(draftKey("rules", 8)), null, "stored draft removed");
});

test("DraftBanner is keyboard-operable and localized", async () => {
  await reset();
  try {
    setLang("ro");
    let restored = 0, discarded = 0;
    mount(html`<${DraftBanner} onRestore=${() => { restored++; }} onDiscard=${() => { discarded++; }} />`);
    await settle();
    const txt = document.getElementById("app").textContent;
    assert.match(txt, /schiță/i, "banner text is Romanian");
    const btns = [...document.querySelectorAll(".draft-banner button")];
    assert.equal(btns.length, 2, "restore + discard buttons");
    btns[0].click(); btns[1].click();
    assert.equal(restored, 1, "restore fires");
    assert.equal(discarded, 1, "discard fires");
  } finally { setLang("en"); unmount(); }
});

test("UX-017: Pager range and ListMeta count go through the catalog", async () => {
  await reset();
  try {
    setLang("ro");
    mount(html`<div><${Pager} offset=${0} limit=${50} total=${200} onPage=${() => {}} />
      <${ListMeta} total=${3} limit=${50} /></div>`);
    await settle();
    const txt = document.getElementById("app").textContent;
    assert.match(txt, /1–50 din 200/, "Pager uses the localized range (din, not 'of')");
    assert.doesNotMatch(txt, /1–50 of 200/, "no hard-coded English 'of'");
    assert.match(txt, /3 element/, "ListMeta uses the localized item count");
    assert.doesNotMatch(txt, /3 items/, "no hard-coded English 'items'");
  } finally { setLang("en"); unmount(); }
});
