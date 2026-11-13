# ADR-0001 — Product name (Klopot), visual identity and where each colour is used

Status: Accepted
Date: 2026-11-08
Amended: 2026-11-09 — Logo reworked to the disc + open-ring + satellite
signal mark on JetBrains Mono Bold (700), converted to outlines (no
web-font dependency).

## Context

The service was born inside the PV-Stack deployment as
`pv-stack-alerts` and has used `alertd` as its process, image and UI
name since 1.0. Both names now work against the project:

- `pv-stack-alerts` says "PV", while the README's first paragraph says
  nothing about the service is PV-specific. The repository is about to
  go public and the name is the first thing a visitor reads.
- `alertd` is a good *process* name (short, Unix-flavoured, obviously a
  daemon) but a poor *product* name: generic, unsearchable, impossible
  to trademark, and meaningless outside the Unix crowd.
- The current favicon is a warning triangle on GitHub-blue. It reads
  as "warning", not "alerting platform", and is indistinguishable from
  a thousand other icons.
- The admin UI already has a token-based theme (`--accent`, `--ok`,
  `--warn`, `--crit`, ...) with a contrast test in
  `tests/js/contrast.test.mjs`, so a brand palette can be applied by
  changing token values, not markup.

The product is an *alerting* tool: red, amber and green already carry
meaning (severity, channel health, delivery status). A brand colour
must not compete with them.

## Decision

### Name

- **Product name: Klopot.** From Romanian *clopot*, "bell" — the
  thing that rings when something needs attention — spelled with a K so
  the written form is one ASCII word on every registry. Pronounced
  **KLO-pot** (stress on the first syllable, both vowels short); publish
  that pronunciation in the README so English speakers do not drift to
  "klop-UT" and Romanian speakers do not write *clopot*. Two syllables,
  six letters, a nod to where the project was born without saying "PV".
  *Kłopot* is Polish for "trouble": a usable story for an alerting tool,
  but one to test with Polish-speaking developers rather than assume.
- **Availability checks, dated 2026-11-08:** PyPI, npm and RubyGems had
  no `klopot`; Docker Hub had no `klopot/klopot`; GitHub had 28
  repositories matching the name, all surnames and empty profiles; a web
  search found no software product of that name. These are
  availability facts, not ownership or trademark clearance. Before the
  name is announced: register klopot.dev (and .com as a redirect if
  free), create the `klopot` GitHub organisation, reserve `klopot` on
  PyPI and npm, and run a trademark search in the EU and US classes for
  software. Record the dates here.
- **Technical name stays `alertd`** through the 1.x line (process,
  log `service` field, `ALERTD_*` environment prefix). This mirrors
  Grafana / `grafana-server` and avoids a breaking change for running
  deployments. In 2.0 the daemon becomes **`klopotd`** — the `d`
  suffix belongs on the process, like `sshd` or `containerd`, never on
  the product.
- **The complete name set.** One word for users, one suffix for
  operators, nothing else:

  | What | Name |
  |------|------|
  | Product, website, wordmark | Klopot · klopot.dev |
  | GitHub organisation and repository | `klopot/klopot` |
  | Container image | `ghcr.io/klopot/klopot` |
  | PyPI package and CLI | `klopot` |
  | Daemon process, log `service` field | `klopotd` (2.0; `alertd` until then) |
  | Environment prefix | `KLOPOT_` (2.0; `ALERTD_` accepted as deprecated alias) |
  | Generated SDKs | `klopot-client` on PyPI, `@klopot/client` on npm |
  | Spelling | "Klopot" in prose; `klopot` (lowercase) in the wordmark and everything machine-readable |

- **Rename plan.** *(Amended 2026-11-09: the public `klopot` repository
  was created fresh from the finalised private tree instead of renaming
  the private one in place; it starts at 1.0.0.)*
  1. Phase 1 (before going public, no code break): repository
     `klopot/klopot`, image `ghcr.io/klopot/klopot`, `pyproject` name
     `klopot`, README/docs/admin-UI brand = Klopot.
  2. Phase 2 (2.0): `klopotd` process name, `KLOPOT_` prefix with the
     `ALERTD_` alias (Pydantic `AliasChoices`). Precedence when both are
     set: `KLOPOT_*` wins and a startup warning names the shadowed
     `ALERTD_*` variable. The alias, the `alertd` image tag and the
     `alertd` console script are removed in 3.0; the deprecation is
     stated in the 2.0 changelog and in `DEPLOY.md`.
  3. Phase 1 is "no code break" only for the API. It does change the
     image name and distribution name, which touches `docker-compose.yml`,
     traefik labels, install scripts and any monitoring that matches on
     the container name. Those are listed in the release plan and the
     old image tag keeps being published for one minor.
  - Not renamed, ever: API paths (`/v1/...`), the `X-API-Key` header,
    the `alertd_session` / `alertd_csrf` cookie names, table names, the
    `alertd.theme` localStorage key. Cosmetic renames there cost users
    and buy nothing.

### Logo

The mark **is the two `o`s in the wordmark** — a declared event becoming
an outgoing notification. The first `o` is a solid **amber source disc**;
the second is an **open amber ring with a detached satellite** at its
upper-right opening, the alert leaving the system for delivery. The word
`klopot` is set lowercase in JetBrains Mono Bold and the two marks occupy
its `o` cells. The open ring and satellite also stand alone as the app
icon. Source files live in `docs/brand/` (its README lists them all and
carries the theme-swap snippet):

| File | Use |
|------|-----|
| `klopot-mark.svg` | App icon: the open ring + satellite on an ink tile. Favicon source, browser tab, sidebar, social preview. |
| `klopot-favicon.svg` | Favicon variant (< 24 px): the ring + satellite, thickened and simplified. |
| `klopot-symbol.svg` | The ring + satellite alone, amber on transparent. |
| `klopot-mark-mono.svg` | The ring + satellite in `currentColor`, no tile. README/docs headers, print, embossing. |
| `klopot-wordmark.svg` / `-dark.svg` | Full wordmark, light / dark. Letters are outlined JetBrains Mono 700 paths — no font dependency. |
| `klopot-lockup.svg` / `-dark.svg` | Wordmark + the `.dev` suffix, light / dark. |
| `concepts.html` | Earlier explorations (Threshold, then disc + locator), kept for the record. |

Geometry (1000-unit em). First `o`: solid disc, Ø510, centred on the
lowercase x-height, optically a touch smaller than the second `o`. Second
`o`: ring Ø550 outer / Ø350 inner (100 thick), opened ~44° toward the 1:30
position with clean radial cuts; a detached Ø150 satellite sits on the
opening's axis, 310 units from the ring centre, with a visible gap. The
ring and satellite must read as one symbol — not a power button, gender
symbol or crosshair. The wordmark is optically kerned after the `o`s are
replaced; it is not mechanically monospaced.

Colour. Both `o`s and the icon symbol are the brand amber **`#FFB31A`** on
every background — amber is the signature and owns the accent. The letters
are off-white (`#F5F6F8`) on dark and near-black (`#0C1016`) on light; the
entire `.dev` suffix stays the neutral secondary text colour (`#ADB4BF` on
dark, `#46505C` on light) and is **never** amber. **The logo carries no
indigo and no red:** indigo is the interface accent and red is reserved
for critical severity; neither belongs in the mark. The logo amber
`#FFB31A` is logo-only and distinct from the UI's `--signal`; the two are
never placed adjacent.

Usage rules:

- Minimum size 16 px for the favicon variant. Keep the opening visible and
  the satellite detached; simplify optically and align to the pixel grid.
  Anywhere the concept matters (sidebar, README, social image) use
  `klopot-mark.svg` or the full wordmark at 24 px or more.
- Clear space around the mark or wordmark: one quarter of its height.
- Never close the ring, re-attach the satellite, recolour off the amber,
  rotate, skew, add shadows, or place the mark on a photograph.
- Wordmark: `klopot` in JetBrains Mono Bold (weight 700), letter-spacing
  −2 %, optically kerned, the disc and open-ring+satellite in its two `o`
  cells. The admin UI embeds the outlined wordmark as inline SVG (letters
  in `currentColor`, the two `o` marks amber); the `docs/brand/` wordmark
  and social card are the same font-independent outlined paths.

### Colour tokens

Two palettes, light and dark, expressed as the CSS custom properties
the admin UI already consumes (`app/admin_ui/static/styles.css`).
Dark is the **primary** theme — the tool is used at night — and both
must pass the contrast test (`tests/js/contrast.test.mjs`): 4.5:1 for
every text colour on the surface it is painted on, 3:1 for `--signal`,
which is only ever a non-text indicator. Two things the token test
cannot see and the stylesheet must therefore state explicitly:
`::placeholder` is `--text-muted` (the browser default grey fails AA on
the dark surface), and translucent tokens are never the only thing
carrying a boundary (the focus ring is opaque; `--focus` is a halo).
The next step for the test is to measure computed styles in a
headless browser, including alpha compositing and the auto-dark media
query, not only literal token pairs.

| Token | Light | Dark | Role |
|-------|-------|------|------|
| `--bg` | `#f6f7fb` | `#0d1117` | Page background |
| `--surface` | `#ffffff` | `#161b22` | Cards, sidebar, topbar, inputs |
| `--surface-2` | `#eef0f6` | `#1f262e` | Hover rows, table header fill, chips |
| `--border` | `#d8dce6` | `#2b3440` | Hairlines |
| `--text` | `#111827` | `#e6edf3` | Body text |
| `--text-muted` | `#5b6475` | `#94a3b8` | Secondary text, labels, hints |
| `--accent` | `#4f46e5` | `#818cf8` | **Brand indigo.** Primary action, active nav, links, focus ring |
| `--accent-text` | `#ffffff` | `#0d1117` | Text on `--accent` |
| `--accent-soft` | `#e8e7fd` | `#1e1b4b` | Active-nav fill, info banners, selected rows |
| `--signal` | `#c2660a` | `#fbbf24` | **Brand amber.** Arrival emphasis only (see below), never a status. This is the in-UI amber; the logo uses its own logo-only amber `#FFB31A` (see Logo) and is unaffected |
| `--ok` / `--ok-soft` | `#136129` / `#dcf5e3` | `#3fb950` / `#12351f` | Healthy, delivered, enabled |
| `--warn` / `--warn-soft` | `#8a5a0d` / `#fff1d6` | `#d29922` / `#3a2d10` | Warning severity, degraded, pending retry |
| `--crit` / `--crit-soft` | `#b02a25` / `#fde3e1` | `#f85149` / `#3d1414` | Critical severity, down, failed, destructive actions |
| `--focus` | `#4f46e566` | `#818cf866` | Focus **halo** only (accent at 40 %). The focus ring itself is an opaque 2 px `--accent` outline so it meets 3:1 on its own |

The severity triplet is unchanged from today; it is already tuned and
tested. Only the neutrals shift slightly toward blue-grey and the
accent moves from generic blue to indigo.

### Where each colour is used

1. **Indigo (`--accent`) identifies actions, selection and informational
   emphasis.** The one primary button per view, links, the active
   navigation item, focus rings, selected rows, the loading bar, the
   default (informational) left border of banners and toasts, the
   highlighted series in a chart. It never encodes an *operational
   condition*: a thing being healthy, degraded, failed, pending or
   disabled is always a severity colour or neutral.
2. **Amber (`--signal`) is arrival emphasis, not a status.** The flash on
   a newly arrived log row and the newest row of the firehose, fading
   within two seconds. (The logo's amber is a separate, logo-only value
   `#FFB31A`; see the Logo section.) It is deliberately
   *not* used to say "connected": connection and stream health use the
   severity colours with a text label (`--ok` "connected", `--warn`
   "reconnecting", neutral "paused"), because a small amber dot and a
   small warning dot cannot be told apart by saturation alone. It is
   never used for text, never on a button, never on a badge.
3. **Red / amber / green (`--crit` / `--warn` / `--ok`) carry operational
   condition only:** severity badges, channel and input health,
   delivery status, breaker state, enabled/disabled, stream state.
   `--crit` is also the colour of *irreversible* actions (delete,
   revoke, purge) so the eye learns one meaning for it. Operational
   recovery actions such as "reset breaker" or "restart input" are
   neutral buttons with a confirmation that says what resumes.
4. **Everything else is neutral.** Chart axes and gridlines are
   `--text-muted` and `--border`; chips that merely name a thing
   (a channel, a type) are `--surface-2` on `--text-muted`.
5. **Badges pair a `*-soft` fill with its strong foreground**
   (`--crit-soft` + `--crit`), never strong-on-strong. Banners and
   toasts use the second accepted pattern: `--surface` with a 4 px
   coloured left border, the border colour following rules 1 and 3.
6. **A new colour literal in `styles.css` or a view is a defect** unless
   it is a new token added to this table by a new ADR.

### Typography

- UI text: the existing `system-ui` stack, unchanged. It keeps the
  strict CSP and native rendering per OS.
- Code, variable names, expressions, ids, numeric table cells:
  `ui-monospace` stack (`--mono`), tabular numerals where supported.
- Wordmark: **JetBrains Mono Bold (700), converted to outlines.** The
  admin UI embeds the outlined wordmark as inline SVG (letters in
  `currentColor`, the two `o` marks in `--wm-amber`), so there is **no
  web-font dependency** — the strict "no network fonts" rule stands and
  `--mono` stays the `ui-monospace` stack. The `docs/brand/` assets are
  the same outlined paths.
- Optional self-hosted Inter for deployments that want a consistent
  look across OSes; off by default.

## Consequences

- The brand was applied to the admin UI on 2026-11-08 (favicon,
  tokens, wordmark, sidebar mark, placeholder and focus styles). The
  JS contrast test covers the token pairs; computed-style testing in a
  browser is listed in the release plan's CI phase.
- The logo was reworked on 2026-11-09, first to a disc + locator mark
  and then to the final **disc + open-ring + satellite** signal mark on
  JetBrains Mono Bold (700), converted to outlines. The `docs/brand/`
  SVG set and the inline UI wordmark were regenerated and the admin UI
  favicon and sidebar updated.
  Text contrast is well clear of AA — letters ~18:1 on their ground,
  `.dev` secondary 9.1:1 (dark) / 7.6:1 (light) — while the amber `o`
  marks are a logo signature, not text, so they are not held to the text
  contrast bar (amber on the light ground is ~1.7:1 by design).
- Code reviews gain a simple rule: a new colour literal in
  `styles.css` or a view is a defect unless it is a new token added to
  this ADR.
- Repository, image and package rename are a coordination task with
  the deploy (`docker-compose.yml`, traefik labels, the GHCR publish
  job in `ci.yml`).
- The `ALERTD_` → `KLOPOT_` env rename is deferred to 2.0 and is the
  only part of this decision that touches running systems.

## Alternatives considered

- **Keep `alertd` as the product name.** Zero rename cost, but it
  fails every brand test (distinct, searchable, protectable) and
  anchors the project to "a daemon" rather than "a product with a UI".
- **Tocsin** (alarm bell) was the first choice and the better word, but
  it is already an active npm package (security advisories for coding
  agents, 2026), a Ruby notification gem, and the name of 50+ GitHub
  repositories including a Matrix notifier for Alertmanager — the same
  niche as this project. A name collision inside our own audience is
  the one kind we cannot afford.
- **Alarum** (archaic "alarm") was the second choice: free on PyPI and
  npm, no software product of that name. Rejected because the `.com`
  domain hosts unrelated content we do not want next to the brand in
  search results.
- **Herald.** Good metaphor for routing to many channels, warmer than
  Klopot, but far more common as a product name and weaker on "alarm".
- **Vigil.** Already used by several monitoring products.
- **Teal palette** instead of indigo. Equally free of severity
  collisions and slightly more distinctive; rejected because indigo
  reads as "infrastructure tooling" to the target audience and gives
  higher contrast on the dark background at the same lightness.
- **Keep the warning-triangle favicon.** Rejected: it encodes the
  wrong noun.
