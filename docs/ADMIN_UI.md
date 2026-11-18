# Admin UI — specification and conventions

The admin UI at `/admin/` is how operators configure and watch Klopot. This
document is its specification: what each screen does and which API it uses,
the shared building blocks, and the rules every change must keep. Read it
before touching `app/admin_ui/static/`.

## Stack and constraints

- **Build-less Preact + htm**, vendored in `static/vendor/` (no bundler, no
  npm at runtime). Views are plain ES modules loaded by the browser.
- **Strict CSP** on `/admin` (`app/admin_ui/__init__.py`): `script-src 'self'`,
  `style-src 'self'`, `connect-src 'self'`. Nothing from a CDN, no inline
  `<script>` or `<style>`; a `style=` attribute on an element is allowed.
- **Same origin, session cookie.** `lib/api.js` sends the cookie and adds the
  CSRF header (`X-CSRF-Token`, double-submit) on every non-GET request. A 401
  logs the user out (`auth:expired`), 403 `PASSWORD_CHANGE_REQUIRED` forces the
  password screen.
- **Colours are theme tokens only** (`--accent`, `--warn`, `--crit`, `--ok`,
  `--*-soft`, `--border`, `--surface`, `--text-muted`…) defined per theme in
  `styles.css`. A new colour literal needs an ADR (ADR-0001 brand, ADR-0002
  theme families); the contrast test checks every theme.
- **Every visible string is an i18n key** (see [i18n](#i18n)).

## Files

| Path | What |
|------|------|
| `index.html`, `app.js` | Shell: auth state machine, sidebar (`NAV`), routes, theme + language pickers |
| `views/<page>.js` | One module per screen (table below) |
| `lib/api.js` | `api.get/post/patch/put/del`, error normalisation (`ApiError`), events |
| `lib/router.js` | Hash router (`#/rules/42?x=y` → path, params, query), nav guard, `useUrlFilters` |
| `lib/loader.js` | `useLoader` — debounced, abortable list loads with `error` (A28, UX-006) |
| `lib/ui.js` | `Drawer`, `Modal`, `ConfirmModal`, `DangerConfirm`, `Spinner`, `Empty`, `ErrorState`, `StaleBanner`, `ListMeta`, `Pager`, `KindHelp`, `DraftBanner`, `useDirty`, `LiveStatus` |
| `lib/dialog.js` | Dialog stack: focus move/trap/return and top-only Escape (`useDialog`) |
| `lib/form.js` | Fields generated from `/v1/meta/kinds`, server 422 → per-field errors, `TagInput`, secrets |
| `lib/draft.js` | Unsaved-draft recovery after a session expiry (UX-007) |
| `lib/action.js` | `useGuard` — one-at-a-time side-effect buttons (UX-016) |
| `lib/select_guard.js` | Ignore out-of-order detail responses (V12) |
| `lib/coalesce.js` | Trailing coalesced trigger for live feeds (UX-012) |
| `lib/ws.js` | Reconnecting WebSocket for `/v1/stream/*` |
| `lib/format.js` | Locale-aware dates, relative times, durations |
| `lib/render.js` | Client-side template preview (mirrors `app/core/rendering.py`) |
| `lib/i18n.js`, `i18n/en.js`, `i18n/ro.js` | `t(key, params)`, `tnode(key)`, catalogs |
| `lib/icons.js`, `lib/icon_picker.js` | Emoji dictionary + validity rule, the icon field with palette |
| `lib/categories.js` | Case-insensitive template categories (`canonicalCategories`, `categoryLabels`) |
| `lib/a11y.js` | `clickable()` row helper, skip link |
| `lib/transfer.js` | `TransferMenu` ("Actions": per-section export + import), `ImportWizard`, and the pieces the Packs page reuses: `downloadPack`, `useDecisions`, `planOf`, `ImportReview`, `ImportDone` |
| `lib/lookup.js` | `lookup(promise, fallback)` for secondary requests (pickers, autocomplete, counts): a failure shows one toast instead of passing for an empty list |
| `lib/stack_tables.js` | Phone tables: `stackTables` / `labelTable` turn a list table into one card per row, labelled from its `<thead>`, keeping table roles |
| `lib/h.js` | The one place that binds htm to Preact (`html`, hooks) |
| `lib/toast.js` | Toast bus (`toast.ok`, `toast.error`, ApiError-aware leads) |
| `lib/json_field.js` | Pure JSON-field validation for the form's JSON inputs |
| `lib/labels.js` | Translated display names for severities, statuses, suppression reasons, health components / codes |
| `lib/palette.js` | Global search (Ctrl+K): `CommandPalette`, `matchScore` |
| `lib/push.js` | Web Push on this device: `pushState`, subscribe / unsubscribe with the service worker |
| `lib/brand.js` | The Klopot wordmark (ADR-0001) |

## Screens

| Route | View | Purpose | Main API |
|-------|------|---------|----------|
| `#/dashboard` | `dashboard.js` | Health, inventory counts, recent alerts, links into filtered lists | `/v1/health` (polled by the shell, `lib/api.js`), `/v1/log/stats`, list totals |
| `#/log` | `log.js` | Notification history, detail drawer, ack, live tail | `/v1/log`, `/v1/stream/notifications` |
| `#/incidents` | `incidents.js` | Active / resolved episodes — from rules, `/v1/fire` idempotency keys and Alertmanager (the drawer shows the source instead of a rule link); ack, resolve | `/v1/incidents` |
| `#/snooze` | `snooze.js` | Mutes and maintenance windows | `/v1/snooze` |
| `#/templates` | `templates.js` | Templates grouped by category; editor with icon palette, live preview, routing, test fire | `/v1/templates`, `/v1/templates/{type}/channels` |
| `#/channels` | `channels.js` | Delivery destinations, test, breaker | `/v1/channels` |
| `#/rules`, `#/rules/:id` | `rules.js` | Rules grouped by template category, status, bulk enable/disable; editor with live validation | `/v1/rules`, `/v1/rules/bulk/enabled`, `/v1/rules/validate` |
| `#/variables` | `variables.js` | Variables grouped by namespace, live value/state, "used by" | `/v1/variables` |
| `#/inputs` | `inputs.js` | MQTT / HTTP / webhook / SMS inputs | `/v1/inputs` |
| `#/schedules` | `schedules.js` | Cron fires with preview | `/v1/schedules` |
| `#/operations` | `operations.js` | Queues, workers, connections, terminal failures | `/v1/operations` |
| `#/state` | `state.js` | Raw state cache + firehose | `/v1/state`, `/v1/stream/state` |
| `#/api-keys` | `apikeys.js` | Machine keys (plaintext shown once) and their restrictions: allowed addresses, requests per minute, allowed alert types | `/v1/api_keys` |
| `#/api` | `api.js` | API reference: every operation, its scope, fields, a curl example | `/openapi.json` |
| `#/audit` | `audit.js` | Who changed what | `/v1/audit` |
| `#/config` | `config.js` | Whole-config YAML export / validate / import | `/v1/config/*` |
| `#/setup` | `setup.js` | First-run setup guide (see below) | `/v1/setup/*` |
| `#/packs` | `packs.js` | Pack catalog, settings form, item review, install | `/v1/packs/*` |
| `#/activity` | `activity.js` | Requests, sources, deliveries, events, keep / ignore rules | `/v1/activity/*` |
| `#/account` | `account.js` + `push.js` | Notifications on this device (Web Push: enable, test, devices — docs/WEB_PUSH.md), password, sessions, preferences | `/v1/auth/*`, `/v1/push/*` |

### Rules page

- The **whole filtered set** (`limit=500`) is loaded and grouped by the
  category of each rule's template; `ListMeta` warns when it is truncated.
  Groups are collapsible and show `N rules · M enabled` plus a
  "need attention" count.
- **Status** comes from the server's `eval_status` (never recomputed in JS):
  `error` = the expression fails (counted towards auto-disable), `no_data` =
  waiting for an input that has no value (not counted), `ok`. Disabled rules
  show their last error as history ("off · last error", audit V21).
- **Banners** list every *enabled* rule with `error`, then with `no_data`,
  across all pages, each name linking to `#/rules/:id`.
- **Filters** live in the URL: `search`, `category` (`__none__` =
  uncategorized), `template_type`, `enabled`, `eval_status`, `never_fired`.
- **Bulk bar** (appears with a selection): Enable / Disable via
  `POST /v1/rules/bulk/enabled` — one transaction, one audit row per changed
  rule, one engine reload. Never loop `PATCH` per rule.
- Rows are **selectable**, so the row is *not* a button: see
  [Rows that open an editor](#rows-that-open-an-editor).

### Variables page

- Loaded whole (`limit=500`), grouped by **namespace** (text before the first
  dot; names without a dot go last as "(no namespace)").
- Groups **start collapsed** (overview of namespaces with counts: stale, no
  value, unused) and **open by themselves while any filter is active**; a click
  flips one group.
- **Filters** in the URL: `search`, `source`, `input_id`, `state`
  (`fresh` / `stale` / `missing`), `used` (`true` / `false`).
- "Used by" = rules (`vars_extract`, `condition_expr`, `recovery_expr`) and
  computed variables (`formula`), including names passed as strings to helpers
  such as `var_age("x")`, `fresh("x", s)`, `has("x")` — computed server-side by
  `app/services/references.py`. The table shows counts; the editor lists them
  as links; deleting a variable still in use warns with the names.

### Rule editor

- The template is a select of existing templates (icon, type, severity); a
  value that is not a template stays selectable, marked "not a template".
- The condition and recovery fields are `ExprInput` (`lib/expr.js`): a list
  under the field completes the word before the caret with variable names and
  functions (`name(`); ↑ / ↓ pick, Enter / Tab insert, Escape closes only the
  list (`useEscapeLayer` puts it on the dialog stack without taking focus).
  `EXPR_FUNCTIONS` there is also the cheat-sheet; a Python test keeps it equal
  to the server's `FUNCTION_NAMES`.
- Timing is a duration: "Send when the condition has held for [D] [unit],
  checking every [S] seconds". The API still stores `persist_n` =
  `floor(D / S) + 1` (`holdToChecks`); the hint names the checks and the
  real delay, and says when D was rounded down. Changing S keeps D.
- After **Validate**, **Try other values** opens a JSON box prefilled with the
  live values the validation reported; it re-validates with `context`
  ("what if"). Nothing is saved.
- **State history** (saved rules): `GET /v1/rules/{id}/transitions`, newest
  first. The list shows `firing` / `pending` in the state column and a
  **Last true** column (`last_true_at`).
- Incident mode stays opt-in; for a plain threshold (`x > 80`) the empty
  recovery field offers a 5 % hysteresis (`x < 76`, `hysteresisFor`).
- Timing reads as a sentence with the two numbers inline — "Send when the
  condition holds for [N] checks in a row, checking every [S] seconds" — and a
  hint with the resulting delay (`(N − 1) × S`).
- Captured values, incidents / recovery, inhibitors and sort order sit in a
  folded "More options"; it opens by itself when the rule uses one of them or
  one has an error.

### Templates page

- Grouped by category, case-insensitively, under the most used spelling
  (`lib/categories.js`; the server canonicalises writes the same way).
- **Icon** = an emoji, chosen from the palette or pasted. Text and
  mis-encoded values (`âš¡`, `??`) are flagged in the list and block Save; the
  server rejects them too. Note `ℹ️` (U+2139) is a *letter* in Unicode and is
  rejected — use 🔵.
- **Routing** marks intrusive channel kinds (`intrusive` from
  `/v1/meta/kinds`: SMS, Pushover) and warns when an `info` template would
  reach one (route enabled, minimum severity `info`) — `intrusiveWarnings()`.
- **Preview context** is built from the placeholders the title and message
  use (`placeholderNames` + `sampleContext` in `lib/render.js`): the current
  value of a variable with that name (`GET /v1/state`), else a sample (a
  number for names that look numeric, `‹name›` otherwise). Editing the JSON
  stops the refill; "Fill in from placeholders" restores it.
- **Delivery gate** (optional fieldset): a variable (suggested from
  `/v1/variables`) and a minimum; the alert is suppressed as `below_gate`
  while the variable is lower. Saving one half without the other is flagged
  on the field. `require_pv_kw` is the deprecated API alias of `gate_min`.

### Import / export ("Actions" menu)

Templates, Rules and Variables have an **Actions** menu (`lib/transfer.js`):

- **Export all** of the section, or **the N shown** with the current filters
  (`GET /v1/config/export?sections=…&names=…`, secrets masked). Templates bring
  their routes. For rules, "include the templates and variables they use" adds
  `with_dependencies=true`; the Rules bulk bar also exports the selection that
  way. Files are named `klopot-<section>[-filtered|-selected]-<UTC stamp>.yaml`.
- **Import from a file…** opens the import wizard, which works for any pack
  (also a full-config export):
  1. choose a YAML file or paste it, then **Preview**
     (`POST /v1/config/import/preview`);
  2. every item is listed per section as **new**, **identical** or
     **different** (with the changed fields: current → incoming, compared as
     import would store them — an omitted field counts as its default);
  3. choose per item — new: Import / Skip; different: **Skip (default)** /
     Overwrite / Import as copy (routes cannot be copied); identical: nothing
     to do. A bulk choice sets the default for every differing item. A new
     route to a template that already exists is marked "adds a channel to a
     template you already have", with a note above the table; its default is
     the server's (`default`): Import for a config import, **Skip** for a
     pack install (docs/PACKS.md). Only choices that differ from the server's
     default are sent ([PACKS.md, "Your routing stays yours"](PACKS.md)).
     "Nothing is saved until you press Apply / Install" stands under the
     counts, and the review ends with what the button will do with the
     current choices — "Apply will: create · overwrite · copy · skip", with
     a count for each (`planOf`);
  4. **Apply** (`POST /v1/config/import/apply`) runs one transaction. Editing
     the text after a preview disables Apply until you preview again.
- Exports are masked (secrets → `env:UNKNOWN_*`, URLs shortened with `…`).
  Re-importing one keeps the live values, so the preview compares through the
  same sanitiser and reports such items as identical — a full export of
  production previews as 100 % identical (verified 2026-11-14).
- Validation errors (e.g. a route to a channel the target doesn't have) are
  shown on the preview; set the items involved to Skip and apply.
- "Import as copy" renames the item `<name>_copy` (`_copy2`, …). A copied
  **template** takes the pack's rules, routes and schedules that point to it;
  a copied rule or variable is renamed only — expressions that mention it are
  not rewritten.

### Setup guide (`#/setup`) and the "Getting started" card

- Four steps: welcome (how sources → rules → templates → channels fit, the
  time zone from `ALERTD_TZ`) → where alerts go (the channel kind picker,
  the channel editor with the kind chosen, then an automatic test send) →
  what to watch (the `script-alerts` pack + a `fire` key + a curl and a
  "send my first alert" button; the sensor / heartbeat packs; Alertmanager)
  → done (the checklist). Progress is `GET /v1/setup/status`, never kept in
  the browser.
- After signing in, an admin landing on the dashboard of an unfinished,
  not-hidden setup is taken to the guide **once per browser session**
  (`sessionStorage alertd.setupShown`). The e2e sessions set that flag; the
  redirect itself is tested in `00_first_run`.
- The dashboard shows `SetupCard` (progress + checklist + Continue / Hide)
  until the setup is complete or hidden. It renders nothing on an error or an
  unexpected response — it must never break the dashboard.
- New channels start with `KindPicker` (cards: icon, product name, the
  kind's `channels.help.<kind>.lead`); `ChannelEditor` takes `initialKind`
  and hands the saved channel to `onSaved(saved)`.

### Activity page (`#/activity`)

- Tabs in `?tab=`: **Requests** (filters method / status / path / key / IP,
  "webhooks only"; a row opens the request with its bodies — admin), **Sources**
  (callers grouped by key / IP + route, status classes, last seen; "Rule…" on a
  row pre-fills an ignore rule; ignored-but-counted list), **Deliveries**
  (`AttemptList`: outcome, HTTP status, Retry-After, the exchange), **Events**,
  **Rules** (ordered list; editor with a 24 h preview).
- `AttemptList` is reused in the Log drawer (timeline of one alert) and the
  channel editor (`ChannelActivity`, last 5, refreshed after a test);
  `InputPayloads` shows the last requests an inbound input received. Bodies
  render only when the server sent them (it strips them for read-only keys).

### Packs page

- Catalog cards (`GET /v1/packs`) with name / description in the UI language
  (`lt()` reads `{en, ro}` texts), tags and item counts; **Install** opens a
  drawer: one field per pack parameter (by type — a channel parameter is a
  select of existing channels, `env` takes a variable name) → **Preview** →
  the same per-item review as config import (`ImportReview` +
  `useDecisions` from `lib/transfer.js`) → **Install**. A route that would
  add a channel to a template you already have is marked and **skipped by
  default** (a config import imports it by default) — see
  [PACKS.md, "Your routing stays yours"](PACKS.md);
  the review ends with "Install will: create · overwrite · copy · skip". Parameter errors from
  the server (`parameter <name>: …`) are shown on that field.
- **Install from a file…** inspects the pasted / uploaded pack, then the same
  drawer. **Create a pack…** downloads a selection (sections, optional names,
  with dependencies) via `/v1/config/export?pack_id=…`.

### API reference page

Reads `/openapi.json` with the session (the JSON is login-gated on a TLS
deploy). Shows each operation's `x-required-scope`, parameters, body fields,
responses and a copyable curl; links Swagger UI (`/docs`) and ReDoc for
"try it out". Swagger's own requests carry the session cookie, so GETs work;
writes need the CSRF header, so use **Authorize** with an API key there.

## Shared patterns

### Lists

```js
const [filters, setF] = useUrlFilters("/rules", query, { search: "", … });   // URL-backed
const [data, loading, reload, error] = useLoader((signal) => api.get("/v1/rules", q, { signal }), [filters]);
// render: error && !data → <ErrorState onRetry=reload/>; data === null → <Spinner/>;
//         empty → <Empty/>; error && data → <StaleBanner/> above the old rows
```

- Load small resources whole and group client-side; use `Pager` only for
  unbounded history (log, audit). A page that loads one `limit=500` page
  shows `ListMeta` ("500 of N") when there are more.
- Picker options, autocomplete and search use `getAll(path, query)`
  (`lib/api.js`): it pages with `skip` until it has every row, so a list never
  stops silently at 500.
- A secondary lookup (options, a count beside a form, live values) goes
  through `lookup(promise, fallback)` (`lib/lookup.js`): the page keeps
  working on the fallback and the operator gets one notice. Never
  `.catch(() => {})` / `.catch(() => [])` — an empty list must not pass for
  "there is nothing". A view's own main list shows `ErrorState` instead.
- Server-side filters for anything an API user would also want; client-side
  only for presentation (grouping, collapse).

### Empty lists

`Empty` (`lib/ui.js`) has three forms — never show a bare "No X match":

- **Nothing exists yet** (`title`, `body`, `actions`): what the page is for,
  what it depends on, and the next step — the page's own "New …" first, then
  `starterActions()` (Install a pack, Open the setup guide) or the page it
  depends on (Variables → Inputs, Schedules → Templates).
- **Nothing matches the filters** (`filtered`, `onClear`): says so and offers
  **Clear filters** (`useUrlFilters` returns the reset as its third value).
- A plain `label` for small inline lists.

### Global search (Ctrl+K)

`lib/palette.js`: a dialog with a combobox (`aria-activedescendant`, ↑ / ↓,
Enter, Escape through the dialog stack). Pages come from `NAV`; templates,
rules, variables, channels, inputs and packs are loaded each time it opens.
`matchScore` ranks a substring above letters in order (typos still find
"chanels"). Opened by Ctrl+K / ⌘K or the Search button (top bar; an icon in
the phone bar). A rule opens its editor (`#/rules/:id`); a template or
variable opens its page filtered (`?search=`).

### Rows that open an editor

- **Plain rows** (no other control in the row): spread
  `clickable(() => setEditing(r), label)` on the `<tr>` — focusable, Enter /
  Space activate (audit F39). The accessible *name* stays the row's visible
  text (WCAG 2.5.3, voice control); `label` goes to `aria-description`. Never
  put an `aria-label` on a control whose visible text says something else.
- **Rows with a checkbox or link**: a `role="button"` row around another
  control is a nested-interactive violation. Make the *name* a
  `<button class="link-btn">` that opens the editor, keep a mouse-only
  `onClick` on `<tr class="row-link">`, and stop propagation in the selection
  cell (`<td class="sel" onClick={e => e.stopPropagation()}>`).
- Links to other screens belong in the editor drawer, not in a clickable row.

### Dialogs, drawers, popovers, menus

- `Drawer`, `Modal`, `ConfirmModal`, `DangerConfirm` register on the dialog
  stack. Escape is handled **once, globally, in the capture phase**, and
  closes only the top-most entry — a local `keydown` handler can never see it
  first.
- A popover or dropdown menu (the icon palette, the Actions menu) must call
  `useDialog(true, onClose, ref)` to get Escape, focus move and focus return;
  otherwise Escape closes the whole drawer.
- Editors: `useDirty` (confirm on close), `useDraft` (recover after a session
  expiry), `useFieldErrors` + `FieldErrorSummary` (server 422 per field).
- Form mistakes never go to a toast. Check before saving with
  `fe.check([[field, ok, msg], …])` — it shows the summary (focused) and marks
  each control; spread `...${fe.attrs(name)}` on the control and put
  `<FieldMsg fe=… name=…/>` under it. Map field → control id in
  `FieldErrorSummary idFor`.
- Toasts are cleared on every route change; they only report the outcome of
  an action on the current page.
- Side-effect buttons use `useGuard` or a `busy` flag — never fire twice.

### i18n

- `i18n/en.js` is the source catalog; `ro.js` mirrors **every** key
  (`tests/js/i18n.test.mjs` enforces parity). Keys are dot-namespaced by
  screen (`rules.*`, `variables.*`, `icons.*`, `api.*`).
- `t(key, params)` for strings with `{placeholders}`, `tnode(key)` for
  structured help (objects / arrays).
- Never concatenate translated fragments into a sentence; add a key with
  placeholders instead.
- Values the API returns as enums or codes (severity, health status and
  component, suppression reason, health `code` + `params`) are shown through
  `lib/labels.js`, never raw; strings live under `labels.*`. A value the
  catalog does not know falls back to the raw value.
- Relative times use `Intl.RelativeTimeFormat` with `style: "short"` (the
  narrow Romanian form is "-9 m").

### Accessibility

- Every control has an accessible name (label, `aria-label`); the axe-based
  `nameViolations()` check runs in the view tests.
- Grouped sections: the toggle is a `<button aria-expanded aria-controls>`.
- Status is never colour-only: badges carry text.
- Touch targets ≥ 44 px under `@media (pointer: coarse)`; links inside
  running text are exempt (WCAG 2.5.8).
- Phone (≤ 860 px): the brand row is the only sticky bar (≈ 56 px: logo,
  health, menu). The desktop top bar is hidden and its controls (`prefs()` in
  `app.js`: language, theme, account, sign-out) render again at the end of
  the menu. On a route change focus moves to `main` without scrolling and the
  page returns to the top.
- Kind forms come from `/v1/meta/kinds`. A field with `show_if:
  {field: [values]}` is shown only for those values (unset = the field's
  default) — `fieldVisible()`; `visibleConfig()` drops hidden non-secret
  values on save. The UI tests render from
  `tests/js/support/meta_kinds.fixture.json`, which must equal the server's
  output (`tests/test_admin_ui.py` regenerates-or-fails).
- On a phone (≤ 640 px) a list table becomes one card per row, each cell
  showing its column name: `lib/stack_tables.js` (started in `app.js`) gives
  every `table.tbl` with a `<thead>` the class `stacked`, a `data-label` per
  cell from its header (a view's own `data-label` wins; an actions or
  selection column gets none) and explicit table roles, which
  `display: block` would otherwise drop in some screen readers. Matrix and
  compact tables (`routing`, `diff`, `compact`) and tables without a header
  keep scrolling inside their own box (`.scroll-x` with `tabindex="0"`, or a
  card holding a `.tbl`) — never the page.

## Testing the UI

`node --test tests/js/*.mjs` (part of `scripts/check.sh`) and the browser
suite `scripts/e2e.sh` (`check.sh --e2e`, CI job `e2e`). Three kinds:

- **DOM tests** with jsdom (`tests/js/support/dom.mjs`: `setupDom`, `mount`,
  `unmount`, `flush`, `nameViolations`). Stub `fetch` per test and route by
  path.
- **Source-contract tests** that read a view's source and assert a pattern
  (e.g. F39, V21). When you refactor the pattern on purpose, update the test to
  the new form and keep its intent in the comment.
- **Browser end-to-end tests** with Playwright (`tests/e2e/*.e2e.mjs`, helpers
  in `support.mjs`) against a throwaway fresh install. They are the contract
  for what jsdom cannot see — layout, real focus, contrast, the phone
  viewport:
  - every route, EN and RO: no console errors or failed requests, exactly one
    `h1`, no English catalog key shown verbatim, no `undefined`/`NaN`, no
    untranslated severity words on a Romanian page, zero axe violations
    (WCAG 2.1 A/AA + best practice);
  - phone (Pixel 7): menu button on screen, sticky top bar ≤ 72 px and not
    covering the `h1`, no horizontal scroll, every control in `main` ≥ 44 px;
  - behaviour: toasts do not survive navigation, saving an empty editor marks
    fields `aria-invalid` and focuses the first one, dashboard cards do not
    clip.

  `scripts/e2e.sh --keep` leaves the stack running; then rerun one file with
  `E2E_URL=… E2E_PASSWORD=… E2E_ADMIN_KEY=… node --test tests/e2e/<file>`
  (`--keep` prints the exact command).

Gotchas:

- Preact runs effects (`useEffect`, hence `useDialog`'s focus move) on the
  **next frame**, which can take longer under a loaded test run: poll for the
  condition (`until(() => …)`, see `tests/js/icon_picker.test.mjs`) instead of
  a fixed `flush(80)`.
- `click()` on a button inside a clickable row bubbles to the row; that is
  exactly what the propagation stops above prevent — test it.
- The view modules import the shell's i18n state; call `setLang("en")` at the
  start of a test and restore it in `finally`.
