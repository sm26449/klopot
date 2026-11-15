import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom } from "./support/dom.mjs";

await setupDom();
const { intrusiveWarnings } = await import("../../app/admin_ui/static/views/templates.js");

const CHANNELS = [{ id: 1, name: "pager", kind: "pushover" }, { id: 2, name: "feed", kind: "ui" }, { id: 3, name: "sms", kind: "sms" }];
const KINDS = new Set(["pushover", "sms"]);

test("warns only when an info alert would really reach an intrusive channel", () => {
  const routes = {
    1: { routed: true, enabled: true, severity_min: "info" },
    2: { routed: true, enabled: true, severity_min: "info" },
    3: { routed: true, enabled: true, severity_min: "warning" },   // info filtered out
  };
  assert.deepEqual(intrusiveWarnings("info", CHANNELS, routes, KINDS), ["pager"]);
  assert.deepEqual(intrusiveWarnings("critical", CHANNELS, routes, KINDS), []);
  assert.deepEqual(intrusiveWarnings("info", CHANNELS, { 1: { routed: true, enabled: false, severity_min: "info" } }, KINDS), []);
  assert.deepEqual(intrusiveWarnings("info", CHANNELS, null, KINDS), []);
});
