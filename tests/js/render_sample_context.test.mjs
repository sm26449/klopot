// Template preview context (lib/render.js): built from the placeholders a
// template uses — live values first, recognisable samples otherwise.
import { test } from "node:test";
import assert from "node:assert/strict";
import { placeholderNames, sampleContext, renderTemplate } from "../../app/admin_ui/static/lib/render.js";

test("placeholder names come from both syntaxes, without filters, once", () => {
  assert.deepEqual(placeholderNames("{host}: {disk.used_pct | fixed(1)}%", "%host% again"), ["host", "disk.used_pct"]);
  assert.deepEqual(placeholderNames("", null, "no placeholders"), []);
});

test("live values win, numeric-looking names get numbers, the rest a visible sample", () => {
  const ctx = sampleContext(["host", "disk.used_pct", "room.temp", "errors"], { host: "nas" });
  assert.deepEqual(ctx, { host: "nas", disk: { used_pct: 87 }, room: { temp: 41.5 }, errors: 3 });
  assert.deepEqual(sampleContext(["whatever"]), { whatever: "‹whatever›" });
});

test("the sample context renders a template with nothing missing", () => {
  const tpl = "{host}: disk {disk.used_pct | fixed(1)}% full";
  const out = renderTemplate(tpl, sampleContext(placeholderNames(tpl)));
  assert.deepEqual(out, { text: "‹host›: disk 87.0% full", missing: [] });
});
