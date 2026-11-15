// The editor preview (lib/render.js) prints a value exactly as the server sends
// it (app/core/rendering.py): half-to-even rounding on the exact binary value,
// the ±12 digit clamp, "{:g}" for floats, errors as [?name|filter]. Expected
// strings come from Python (tests/core/test_rendering.py checks the fixture).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderTemplate } from "../../app/admin_ui/static/lib/render.js";

const cases = JSON.parse(readFileSync(new URL("./support/render_parity.json", import.meta.url), "utf8"));

test("the preview renders every shared case like the server", () => {
  const wrong = cases.filter((c) => renderTemplate(c.template, c.context).text !== c.expected)
    .map((c) => `${c.template} ${JSON.stringify(c.context)} → ${renderTemplate(c.template, c.context).text} (server: ${c.expected})`);
  assert.deepEqual(wrong, []);
});
