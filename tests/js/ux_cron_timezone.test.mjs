// UX-010 / R3: the cron preview labelled the next-fire times with the server's
// zone (e.g. "(UTC)") but formatted the instants in the *browser's* zone, so a
// 22:00Z fire showed as "12:00 AM (UTC)" in Europe/Bucharest. fmtDateTime now
// takes a `tz` so the instant is rendered in the labelled zone — across any
// offset and DST — and falls back safely on an unknown zone.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fmtDateTime } from "../../app/admin_ui/static/lib/format.js";

// A runner-TZ-independent baseline: what Intl renders for an instant in a zone.
const inZone = (iso, timeZone) =>
  new Date(iso).toLocaleString("en", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone,
  });

// Intl separates the time and the day-period with a narrow no-break space in
// current ICU; match it (and a plain space) with \s.
const PM10 = /10:00:00\s*PM/i;
const AM12 = /12:00:00\s*AM/i;
const AM01 = /01:00:00\s*AM/i;

test("renders the instant in the given zone, matching the label", () => {
  const iso = "2026-11-09T22:00:00Z";
  // UTC: the wall clock equals the instant's UTC time.
  assert.equal(fmtDateTime(iso, { tz: "UTC" }), inZone(iso, "UTC"));
  assert.match(fmtDateTime(iso, { tz: "UTC" }), PM10);
  // Bucharest in November is UTC+2 → 00:00 next day, and it must NOT equal the
  // UTC rendering (that mismatch was the bug).
  const buch = fmtDateTime(iso, { tz: "Europe/Bucharest" });
  assert.equal(buch, inZone(iso, "Europe/Bucharest"));
  assert.notEqual(buch, fmtDateTime(iso, { tz: "UTC" }));
  assert.match(buch, AM12);
});

test("is DST-aware: the same zone shifts between winter and summer", () => {
  const winter = fmtDateTime("2026-11-09T22:00:00Z", { tz: "Europe/Bucharest" }); // +2 → 00:00
  const summer = fmtDateTime("2026-07-01T22:00:00Z", { tz: "Europe/Bucharest" }); // +3 → 01:00
  assert.match(winter, AM12);
  assert.match(summer, AM01);
});

test("an unknown zone falls back to the browser zone instead of throwing", () => {
  const iso = "2026-11-09T22:00:00Z";
  assert.doesNotThrow(() => fmtDateTime(iso, { tz: "Not/AZone" }));
  assert.equal(fmtDateTime(iso, { tz: "Not/AZone" }), fmtDateTime(iso));
});

test("no tz keeps the original browser-zone behaviour (back-compat)", () => {
  const iso = "2026-11-09T22:00:00Z";
  assert.equal(fmtDateTime(iso), fmtDateTime(iso, {}));
  assert.equal(fmtDateTime(""), "—");
  assert.equal(fmtDateTime("not-a-date", { tz: "UTC" }), "not-a-date");
});
