# ADR-0002 — Optional OS-native theme families

Status: Accepted
Date: 2026-11-09

## Context

ADR-0001 fixes the Klopot palette: indigo `--accent` for interaction,
amber `--signal` for "live" indicators only, and red/amber/green
`--crit`/`--warn`/`--ok` for severity. It is applied through CSS custom
properties in `app/admin_ui/static/styles.css` with a single light/dark
pair and an AA contrast test in `tests/js/contrast.test.mjs`.

Operators run the admin UI next to other tools all day and asked to make
it feel native to their desktop. We already maintain a mature, AA-tuned,
multi-family theme system in a sibling project (`sm26449/webterm`):
macOS, Windows 11, GNOME (libadwaita) and KDE (Breeze) palettes, each in
light and dark, every colour chosen for WCAG contrast and covered by a
contrast test. Reusing those palettes is cheap; the question is how to
add them without diluting the Klopot brand that ADR-0001 just fixed.

ADR-0001 says a later decision that changes the palette needs its own
ADR. This is that ADR — but it *adds* choices rather than changing the
default, so it amends rather than supersedes.

## Decision

- **Klopot stays the default family and the brand, unchanged.** A fresh
  install, and every existing user, sees the exact ADR-0001 palette. The
  wordmark, favicon and marketing keep indigo + amber.
- **Add four opt-in families — macOS, Windows, GNOME, KDE — each in
  light and dark.** They are selectable in the admin UI only; they are
  not the brand and are not used in any public-facing asset.
- **Families borrow chrome and accent, not semantics.** Each family
  takes its background/surface/text scale and its accent (the OS link
  blue) from the host OS palette. The severity tokens
  (`--ok`/`--warn`/`--crit`) and `--signal` stay Klopot's, constant
  across every family, so an alert's severity reads identically whatever
  theme is chosen. Severity must never depend on the operator's skin.
- **Borrow colour, not skin.** We port palette values only — not
  webterm's glass/vibrancy, window shadows, gradients or OS font stacks.
  Klopot keeps its flat surfaces and its own system-font stack. The goal
  is a familiar accent and chrome tint, not an OS mimicry.
- **Theme = family × mode.** `mode` is auto/light/dark (auto follows
  `prefers-color-scheme`, live). `app.js` resolves the pair and writes
  `data-theme="<family>-<mode>"` (e.g. `macos-dark`); Klopot keeps the
  legacy contract (`""` = auto, `"light"`, `"dark"`) so nothing about the
  default path changes. Stored as `alertd.family` + `alertd.theme`
  (mode); an old `alertd.theme` value alone resolves to Klopot + that
  mode, so upgrades are seamless.
- **Every family block meets the same AA pairs as Klopot**, enforced by
  `tests/js/contrast.test.mjs` across all ten variants. Tokens webterm
  lacks (`--accent-soft`, `--accent-text`, the severity soft
  backgrounds, `--signal`) are derived and validated to the same
  thresholds.

## Consequences

- Operators get a native-feeling UI; the brand is untouched. New colour
  literals still need an ADR — this one authorises exactly these four
  families and no more.
- `styles.css` grows by eight token blocks. They are generated from a
  compact spec and the contrast test is the gate, so adding or retuning a
  family is mechanical, not hand-eyeballed.
- A new severity or chrome token must be added to **every** family block
  (and to the test's pair list), or the family falls back to an
  inherited value. The contrast test fails loudly if a block is missing
  a pair.
- Documentation, screenshots and the social card stay in the Klopot
  default so the brand stays coherent.

## Alternatives

- **Replace the Klopot palette with an OS-native one** — rejected: it
  throws away the ADR-0001 identity (indigo + amber, the bell mark) for
  no gain; the brand is the first thing a visitor sees.
- **One combined picker entry per variant** (ten flat options) —
  rejected: family × mode is fewer choices, keeps "follow the OS"
  working per family, and matches how people think ("I want it to look
  like my Mac, in dark").
- **Import webterm's full theme engine (Tailwind, glass, fonts)** —
  rejected: the admin UI is build-less Preact + htm with a strict CSP
  and flat surfaces; only the palette values transfer cleanly, and a
  skin would fight Klopot's own visual language.
