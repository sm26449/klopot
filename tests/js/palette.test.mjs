// Global search ranking (lib/palette.js matchScore).
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupDom } from "./support/dom.mjs";

await setupDom();
const { matchScore } = await import("../../app/admin_ui/static/lib/palette.js");

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
