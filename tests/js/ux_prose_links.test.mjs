// UX-005: a link inside running text (e.g. the OpenAPI link in Account) was
// distinguishable from the surrounding text by colour alone — axe
// link-in-text-block, WCAG 1.4.1. Links inside <p> must carry a permanent
// underline; nav/action/card links sit outside <p> and keep their styling.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(
  fileURLToPath(new URL("../../app/admin_ui/static/styles.css", import.meta.url)), "utf8");

test("links in prose (p a) are permanently underlined", () => {
  const m = css.match(/\bp a\s*\{[^}]*\}/);
  assert.ok(m, "no `p a` rule found");
  assert.match(m[0], /text-decoration:\s*underline/,
    "`p a` must set text-decoration: underline (non-colour link indicator)");
});

test("the account OpenAPI link lives in a <p> so the rule applies", () => {
  const view = readFileSync(
    fileURLToPath(new URL("../../app/admin_ui/static/views/account.js", import.meta.url)), "utf8");
  // the env note is a <p> containing openApiLink
  assert.match(view, /<p[^>]*>[^]*openApiLink[^]*<\/p>/,
    "the OpenAPI link should be inside a <p> (prose) so p a underlines it");
});
