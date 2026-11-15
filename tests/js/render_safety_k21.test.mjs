// Review K21: the editor preview (lib/render.js) must render like the server
// (app/core/rendering.py) and must not touch Object.prototype.
import { test } from "node:test";
import assert from "node:assert/strict";
import { sampleContext, renderTemplate } from "../../app/admin_ui/static/lib/render.js";

test("a __proto__ placeholder cannot pollute Object.prototype", () => {
  sampleContext(["__proto__.polluted", "constructor.prototype.polluted2", "a.__proto__.polluted3"]);
  assert.equal(({}).polluted, undefined);
  assert.equal(({}).polluted2, undefined);
  assert.equal(({}).polluted3, undefined);
});

test("one pass, like the server: a value is never expanded again", () => {
  const out = renderTemplate("{a} %b%", { a: "%b%", b: "x" });
  assert.equal(out.text, "%b% x");
  assert.equal(renderTemplate("%a% {b}", { a: "{b}", b: "x" }).text, "{b} x");
});

test("inherited properties are not values", () => {
  const out = renderTemplate("{constructor} {toString} {x.constructor}", { x: {} });
  assert.equal(out.text, "[?constructor] [?toString] [?x.constructor]");
  assert.deepEqual(out.missing, ["constructor", "toString", "x.constructor"]);
});
