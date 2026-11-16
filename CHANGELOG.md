# Changelog

All notable changes to Klopot are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Upgrade notes

- **`compose.traefik.yml` is private by default.** Only clients in
  `KLOPOT_PRIVATE_CIDRS` (default: loopback and the private ranges) reach
  the hostname; others get `403` from traefik. If you reach Klopot from a
  public address today, list your networks in `KLOPOT_PRIVATE_CIDRS`, or open
  only `POST /v1/fire` with the new `compose.public.yml`. A file-provider
  route copied from `deploy/traefik/klopot.example.yml` needs the same
  `klopot-private` middleware to get this behaviour.
- **`ALERTD_TRUSTED_PROXY_CIDRS` is required by `compose.traefik.yml`**, and
  an invalid entry or a `/0` now stops Klopot at startup (it used to be
  logged and skipped).
- **`test: true` on `/v1/fire` no longer lifts the silencing for a `fire`
  key.** It still marks the alert as a test; only an `admin` key or session
  also skips throttle, the delivery gate, quiet hours and de-duplication. A
  producer's "send a test" button keeps working, but a test is now throttled
  among tests (`min_repeat_min`), and `suppressed_reason` says when one was
  held. Migration `0040` (adds `throttle_state.is_test`) runs on startup.
- **Inbound inputs (webhook, SMS inbox, Alertmanager) require their token**
  unless their config says `auth_required: false`. Migration `0041` keeps
  every existing input's behaviour: one that had no token and no flag was
  open to anyone and now says `auth_required: false` explicitly — the
  Inputs page marks it "no token"; set a token, or keep it for a sender on
  your own network. Saving an input that requires a token without one is
  refused with `422`; a config import is refused the same way.
- **An inbound input's token needs at least 32 characters** when it is set
  or changed (REST, admin UI, import). An input saved with a shorter one
  keeps working and can still be edited, disabled, exported and restored as
  it is; the Inputs page marks it "short token" until you set a new one
  (`openssl rand -base64 32`) and give it to the sender. The refusals of the
  inbound endpoint are now one `401`, budgeted per address (see Security).
- **Alertmanager: the type label chooses only among `label_types`.** A
  template named like the alert's `alertname` used to be chosen whatever it
  was, so a token holder could pick any template (one that pages by SMS).
  Now the label picks a template only if `label_types` lists it (names or
  patterns like `am_*`); empty = severity and `default_type` decide, as the
  shipped pack already does. List the templates if you relied on the label.

### Added

- **Per-key source allowlist**: an API key can be limited to IPs / CIDRs
  (IPv4 and IPv6) — API keys → the key → *Allowed addresses*, with "Add my
  address" — or `allowed_cidrs` on `/v1/api_keys`. From anywhere else it
  gets `403` and counts as a wrong key for that address; checked on every
  request, cached or not, HTTP and WebSocket; rotation keeps it; a change
  applies at once. Empty = any address, as for every existing key
  (migration `0042`). `GET /v1/auth/me` returns `client_ip`.
- **Per-key rate limit**: `rate_limit_per_min` on an API key (API keys → the
  key → *Requests per minute*). A quiet key may send that many at once, then
  one every 60/N seconds; over it, `429` with `Retry-After` — the seconds
  until the next request fits. Counted per key on every request, HTTP and
  WebSocket, and not as a wrong key; an edit or the resolve cache never
  refills it; rotation keeps it. Empty = no limit, as for every existing key
  (migration `0043`). Metric `alertd_api_key_rate_limited_total{key}`.
- **Alertmanager budgets**: `max_new_episodes_per_min` (default 60) and
  `max_active_episodes` (default 500) per input — a firing alert past either
  is not opened now (`over_budget` in the response and the
  `alertmanager_truncated` notice) and Alertmanager re-sends it; `max_alerts`
  is capped at 1000. Each new fingerprint used to open an episode and a
  notification without limit.
- **Per-input rate limit** for webhook, SMS inbox and Alertmanager inputs:
  `rate_limit_per_min` in the input's config (Inputs → the input). Counted
  like an API key's, after the token; over it, `429` with `Retry-After`.
- `compose.public.yml`: accept alerts from the internet — opens exactly
  `POST /v1/fire`, with a per-client rate limit, an overall in-flight limit
  and a 64 KiB body limit in traefik (docs/DEPLOY.md, "Exposing /v1/fire to
  the internet"). Checked against traefik v3.

### Security

- `test: true` turned any `fire` key into an unthrottled pager (it skipped
  throttle, quiet hours, the delivery gate, the duplicate claim and the
  per-type cooldown). The test flag is now only a tag: test fires are
  claimed and throttled in a pool of their own (`throttle_state` keyed on
  `(type, is_test)`, like `dedup_claims`), so a test never delays or absorbs
  a real alert, and lifting the silencing is an administrator's privilege.
- An inbound input without a token accepted posts from anyone, and the API
  saved one without a word. A token is now required by default and checked
  when the input is saved; `auth_required` must be a boolean (the string
  "false" used to mean "required").
- The inbound endpoint (`POST /v1/inputs/{id}/webhook`) revealed which ids
  are live inputs (`404` vs `401`), and wrong tokens were never budgeted. Now
  a missing, other-kind or disabled input and a wrong or missing token all
  get the same `401` ("Unknown input or wrong token"), and count against the
  address: five a minute, then `429` with `Retry-After` — a budget separate
  from the API keys'. The input's editor lists the refused requests.
- `POST /v1/fire` bounds its `context`: at most `ALERTD_FIRE_CONTEXT_MAX_BYTES`
  (default 16 KiB) as compact JSON and 16 levels deep, `422` beyond. It is
  stored, hashed and rendered for every fire — even of an unknown type — and
  only the 1 MiB request cap bounded it.
- Proxy trust fails closed: `ALERTD_TRUSTED_PROXY_CIDRS` is parsed once at
  startup with the parser every request uses; a typo no longer turns into
  "trust nothing" silently, and IPv4-mapped IPv6 peers match their IPv4
  network. A TLS deployment without trusted proxies logs a warning at
  startup. The setting is shown on the Settings page.
- Dev tooling: Playwright 1.48.2 → 1.61.1 (GHSA for < 1.55.1: browsers were
  downloaded without checking the TLS certificate). Test-only; not in the
  image. 1.61 is the last line that runs on Node 18; 1.62+ needs Node 20.

### Fixed

- Search (Ctrl+K): when the results arrived after you started typing, the
  list re-sorted and Enter opened whatever had moved under the highlight;
  the highlight now stays on the item you saw.
- Focus: a page change no longer takes focus from an open dialog. Search
  (Ctrl+K) opened right after closing a drawer lost its input to the page,
  so Enter went nowhere; a drawer opened from a link (`#/rules/12`) now
  keeps focus on its first field.
- Tests: the concurrent-login pool check (K07) on MySQL is deterministic.

## [1.1.1] — 2026-11-15

Hardening after the pre-open-source audits: no publicly known default
credential, provider settings that were fixed in the code, a UI that says
when something failed to load. Read the upgrade notes before upgrading.

### Upgrade notes

- **No default database password.** `ALERTD_DATABASE_URL`, `MYSQL_PASSWORD`
  and `MYSQL_ROOT_PASSWORD` have no defaults any more (they were `alertd`):
  Klopot refuses to start without the URL, and the bundled MySQL without its
  passwords. An install that relied on the default must set them in `.env`
  (and, to keep the data, set them to the password the database already has).
- **Escalation is off unless you name a channel.** `ALERTD_ESCALATION_CHANNEL`
  defaulted to `sms_main`; it is now empty. If you escalate through
  `sms_main`, set `ALERTD_ESCALATION_CHANNEL=sms_main` in `.env` **before**
  upgrading, or unacknowledged criticals stop being re-paged.
- **Demo:** export a random `ALERTD_BOOTSTRAP_ADMIN_KEY` before
  `docker compose -f compose.demo.yml up` (the README shows the command);
  the demo no longer ships a fixed key. The dev overlay takes its passwords
  from `.env` too.

### Security

- Telegram goes through `safe_http` like every other channel (egress
  screening, IP pinning, no redirects, response cap); it used a plain httpx
  client.
- No publicly known credential is a default: the database URL and MySQL
  passwords (above), the demo admin key and the dev admin password. The MySQL
  healthcheck passes the password through `MYSQL_PWD`, not as a `-p`
  argument that `ps` shows.
- SMS channel healthcheck: a failed check returned the raw error text, in
  which httpx quotes the URL — a health or router URL with a token reached
  anyone with a read-scoped key. It now returns the redacted text.
- Pushover: a receipt that cannot be read (revoked token, HTTP error,
  network) is logged as a warning without the token, instead of silently
  leaving an emergency acknowledged in the app open in Klopot.

### Added

- Channel settings that were fixed in the code: `api_url` for Telegram (a
  self-hosted Bot API server), Pushover and Twilio, with today's addresses as
  defaults; `timeout_sec` for Telegram and SMS. `ALERTD_SNOOZE_MORNING_HOUR`
  (default 8) sets the "snooze until morning" hour, and the Telegram button
  label follows it.
- README screenshots of the admin UI (`docs/screenshots/`), generated from
  synthetic data by `scripts/screenshots.sh`; `scripts/e2e.sh` takes
  `E2E_AFTER` (a command run on the throwaway stack) and `E2E_ONLY=none`.

### Changed

- CI runs Node 24 LTS (from `.nvmrc`) with `actions/setup-node@v7`; it ran
  Node 20, past its end of life, through a deprecated action. The admin-UI
  test harness works on Node 21+ too (`navigator` became a read-only global).
- ntfy, Gotify, Pushover and webhook share one request / health-check path
  (`app/channels/_http.py`) instead of four copies of the same error
  handling. A webhook transport error now reads `webhook HTTP error: …`.
- Admin UI on a phone: list tables (alerts log, incidents, rules, variables,
  API keys, audit, push devices…) become one card per row below 640 px, each
  value under its column name, instead of a table scrolling sideways with
  clipped titles and squeezed selects. Matrix and compact tables still scroll
  inside their box; screen readers keep the table semantics.

### Fixed

- Admin UI: a list that fails to load is said, not shown as empty. Picker
  options, autocomplete and live values give one "some lists couldn't be
  loaded" notice; Ctrl+K says when a section is missing; the rules page says
  when it could not check which rules are failing (it showed none); delivery
  attempts and recent payloads show an error instead of "no rows"; a channel
  whose usage could not be read shows `?` routes, not `0`.
- Admin UI: pickers, autocomplete, Ctrl+K, the "rules needing attention"
  banners and the API keys list load every page instead of stopping silently
  at the first 500 (100 for the banners).
- Config import refuses input kinds that have no adapter (`schedule`,
  `email_imap`), as the API already did; the input form no longer offers
  them, and an existing one is logged as not started.
- Activity log: a failed load of the rules was logged at debug and the empty
  set kept for 60 s, so ignore / keep rules silently did not apply; it is now
  a warning (once per outage) and retried after 5 s.
- HTTP poll: an answer that looks like JSON but does not parse is logged
  (once per run of bad answers) instead of silently used as text.
- Template editor preview: numbers now look exactly as sent. The preview
  rounded half up (`2.5` → `3`, the server sends `2`), did not clamp digit
  counts (`fixed(101)` showed an error), printed full floats where the server
  prints six significant digits (`0.333333`) and treated `div(0)` or
  non-numeric text as numbers. 43 shared cases
  (`tests/js/support/render_parity.json`) keep the two in step.
- Template icon: the editor accepts exactly what the API accepts (`‼` passed
  the editor and was refused with 422; `✓` and `°` were refused by the editor
  only); shared cases in `tests/js/support/icon_parity.json`.
- Webhook: `timeout_sec`, offered in the channel form, was ignored (always
  10 s). MQTT publish used a fixed 256 KiB limit instead of
  `ALERTD_MQTT_MAX_PAYLOAD_BYTES`, the limit inbound MQTT already used.
- Search (Ctrl+K): text typed right after the palette opened could be wiped
  by its reset; the reset now runs when the palette closes.
- Activity log: a rule created or changed was ignored for up to a minute on
  a host up for less than a minute (the rule cache took "loaded at 0" for
  fresh, and `monotonic()` counts from boot); a load racing a change no longer
  keeps the old rule set either.
- Admin UI: JSON blocks (the why-fired drawer) are keyboard-focusable, so a
  wide value that scrolls sideways can be reached without a mouse.
- CI: `scripts/generate_sdks.sh` finds `openapi-python-client` on `PATH` when
  there is no `.venv` (the GitHub runner), and the browser e2e runs with
  reduced motion and waits for state instead of checking it once, so a slow
  runner no longer fails axe on a drawer still sliding in.

## [1.1.0] — 2026-11-15

Schema `0028`–`0039`, applied on startup, forward-only: take a backup first
(`scripts/deploy.sh` does). Read the upgrade notes below before deploying;
[project status](docs/PROJECT_STATUS.md) summarises the release.

### Upgrade notes

- **Rotate** the credentials that were in use while the Activity log was
  enabled before this release (Pushover token and user key, webhook URLs with
  a secret path): rows written before the upgrade keep them until they expire.
- **ntfy `topic` is write-only** now (on ntfy the topic name is the
  credential): the API and exports return it masked. It may also come from
  `topic_ref`.
- **Secrets** resolved from `*_ref` or literal fields are trimmed; one with a
  control character inside is refused and the send fails as a missing secret
  — the log names the variable (`secret env … contains a control character`).
- **Expressions** that a rule or computed variable could store before are
  refused now: `sum()` of anything but numbers, `round(x, n)` with `|n|` over
  100, more than 1,000,000 elements or characters built by `*` / `+` in one
  evaluation, triple-quoted strings, control characters. Check stored rules
  with `POST /v1/rules/validate` before upgrading.
- **Inbound webhook** `POST /v1/inputs/{id}/webhook`: an id that is not a
  webhook-kind input answers `404` (was `400` with the input's name); the
  token is checked before a `503` for a stopped adapter.
- **Sign-in** may answer `503` with `Retry-After` while more than 16 sign-ins
  wait for password hashing.
- **MQTT brokers** at a metadata, link-local, multicast or unspecified
  address are no longer contacted (private addresses are fine).
- **`ALERTD_BOOTSTRAP_ADMIN_KEY`** in the generated shape must be random
  (generate it as `.env.example` shows); a visibly non-random one is ignored.
- **`BACKUP_CRON`** minute and hour must be `*`, a number or `*/N`; the backup
  sidecar refuses anything else at start.
- **Container images:** `:latest` and `:v<version>` are published from release
  tags only; builds of `main` are `:edge`.

### Added

- Web Push without an app (docs/WEB_PUSH.md): the admin UI installs as an
  app (manifest, icons, a service worker that only shows notifications and
  opens them — no offline cache) and receives alerts as system
  notifications, on iPhone / iPad from the Home Screen app (iOS 16.4+).
  Account → "Notifications on this device" enables it, tests it and lists
  every device (rename, minimum severity — `warning` by default — pause,
  remove); the setup guide offers it in step 2. API `/v1/push/config` and
  `/v1/push/subscriptions` (migration 0033, table `push_subscriptions`).
  Sending goes through `safe_request` to allowlisted push services only
  (`ALERTD_PUSH_ALLOWED_HOSTS` for more), end-to-end encrypted; a device the
  push service reports gone is removed, 429 defers. The public VAPID key is
  derived from the private one (`scripts/vapid_keys.py`,
  `KLOPOT_SECRET_VAPID_PRIVATE`).
- **Activity log** (migration `0032`, `docs/ACTIVITY_LOG.md`): every request
  Klopot receives (who, from which IP, route, status, duration, trace id;
  bodies for alerts, webhooks and errors, secrets never), every attempt to a
  provider with its HTTP exchange (`Retry-After`, status, response), and state
  changes of inputs, rules and channels. Rules editable in the admin UI decide
  what is kept: per pattern (method, path glob, status, key, IP) keep for N
  days or ignore (counted only). An Activity page (Requests, Sources,
  Deliveries, Events, Rules), the attempts timeline in the Log drawer, and the
  latest activity in the channel and input editors. Retention follows
  `log_retention_days`; health and metrics probes are kept one day by preset
  rules.
- Alertmanager / Grafana receiver: an input of `kind: alertmanager` takes
  Alertmanager v4 and Grafana alert groups on `POST /v1/inputs/{id}/webhook`
  (token as `X-Input-Token` or `Authorization: Bearer`). Each alert is an
  episode: firing notifies once, re-sends notify nothing, resolved closes it
  and can send a resolution template; a late resolve cannot close a newer
  episode. Template by alertname, then severity, then a default — unknown
  alerts are never dropped.
- Episode lifecycle on `POST /v1/fire`: `idempotency_key`, `status`
  (`firing` / `resolved`) and `resolved_type`; the response adds
  `incident_id` and `episode` (`opened` / `repeat` / `resolved` / …).
- Native ntfy channel (`kind: ntfy`): severity → priority, UTF-8 titles with
  the template icon, tags, click link and View button to the admin UI; the
  ntfy message id is stored on the delivery.
- External episodes on `incidents` (`source_kind`, `source_key`) and
  `deliveries.provider_ref`; migration `0028`. The incident drawer shows the
  source of external episodes.
- A shared fire service behind every entry point.
- Native Gotify (`kind: gotify`) and Pushover (`kind: pushover`) channels.
  Pushover emergency priority (repeat until acknowledged) is opt-in per
  severity; acknowledging in Klopot cancels the emergency, acknowledging in
  the Pushover app acknowledges the alert in Klopot. Migration `0029`.
- Generic provider lifecycle: durable `lifecycle_commands` and a deduplicated
  `inbound_events` inbox, run by a new `lifecycle` worker (shown in
  Operations and `alertd_worker_up`).
- Channel kinds report `intrusive` in `/v1/meta/kinds`; the template editor
  marks them and warns when an `info` template would reach one.
- Client SDKs generated from `openapi/v1.json`: Python `klopot-client` and
  TypeScript `@klopot/client` (fetch wrapper with `fire()` / `resolve()`), in
  `sdk/`, with a drift check in `scripts/check.sh` and CI.
- Adapter test kit (`tests/channels/_kit.py`); channel errors scrub known
  secret values.
- `docs/SCHEMA.md` is checked against the models by a test; the documented
  schema was brought up to date (missing columns, lengths, enum values).

- API reference page in the admin UI (System → API reference): every endpoint
  grouped by resource, with the key scope it needs, parameters, body fields,
  responses and a copyable curl command; linked from API keys and the dashboard.
- The OpenAPI schema marks each operation's required scope (`x-required-scope`).
- Icon palette in the template editor: ~90 emoji grouped by meaning, searchable
  in English and Romanian, with a live preview; invalid icons are flagged in
  the template list.
- Per-section import / export: an "Actions" menu on Templates, Rules and
  Variables exports all, the filtered items or (rules) the selection with the
  templates and variables they use; the import wizard previews every item as
  new / identical / different with the changed fields and lets you skip
  (default for existing items), overwrite or import as a copy.
  `GET /v1/config/export` takes `sections`, `category`, `names` and
  `with_dependencies`; new `POST /v1/config/import/preview` and
  `POST /v1/config/import/apply`.
- Rules page grouped by template category (collapsible, with per-group counts
  and issues), filters for category and firing history, and bulk
  enable/disable through `POST /v1/rules/bulk/enabled` (one transaction, one
  audit entry per rule, one engine reload).
- Variables page grouped by namespace (collapsed overview, opens while
  filtering), filters by input, value state and usage, a "Used by" column and
  the list of reading rules / computed variables in the editor; deleting a
  variable that is still read warns with those names. `GET /v1/variables`
  returns `used_by_rules`, `used_by_variables` and `value_state`
  (`fresh`/`stale`/`missing`) and filters on `state`, `input_id` and `used`;
  `GET /v1/rules` filters on `category` and `never_fired`.
- Rules carry `eval_status` (`ok`, `no_data`, `error`) and `GET /v1/rules`
  filters on it. The Rules page tells a failing expression apart from a rule
  waiting for an input, and its banners list every affected enabled rule.
- Browser end-to-end tests (`scripts/e2e.sh`, `tests/e2e/`, Playwright):
  a throwaway fresh install, first login, every page in English and
  Romanian (errors, failed requests, leaked strings, axe), a phone viewport
  and editor behaviour. `scripts/check.sh --e2e` and a CI job run them.
- Health components carry a stable `code` and `params` next to the English
  `detail`, so clients can show them in another language.
- SMS channel providers (migration `0031`): `http` (any gateway with an HTTP
  API — URL, method, body template with `{phone}` / `{text}`, bearer / basic /
  custom-header auth, optional health URL), `twilio` and `teltonika` (a RUT
  router's REST API). `phone` takes several numbers; `max_chars` sets the cut.
  Existing SMS channels in the old `gateway_url` shape are converted to `http`
  with the same request, and the old shape is still accepted on write and
  import.
- Admin UI: empty lists say what the page is for, what it needs and what to
  do next (with buttons); a filter with no match offers **Clear filters**.
  Global search with **Ctrl+K / ⌘K** (or the Search button) over pages,
  templates, rules, variables, channels, inputs and packs. The rule editor
  picks the template from a list, phrases timing as a sentence ("for 3
  checks in a row, checking every 30 seconds — about 1 min") and folds the
  advanced options. The template preview fills its context from the
  template's own placeholders, with live variable values where they exist.
  Links inside text are underlined.
- **Setup guide**: after the first sign-in a new installation opens a
  four-step guide — how Klopot works, where alerts go (pick a channel kind
  from cards, save, an automatic test send), what to watch (alerts from your
  own scripts with a ready API key and curl, MQTT sensor / heartbeat packs,
  Alertmanager), and a checklist. `GET /v1/setup/status` derives each step
  from the live configuration; `POST /v1/setup/dismiss` / `reopen` hide or
  show it. The dashboard shows a "Getting started" card until setup is
  complete. Channel tests are audited (`channel.test`). New catalog pack
  `script-alerts`.
- **Packs** (`docs/PACKS.md`): configuration with a `pack:` header and
  typed parameters (`${name}`). A built-in catalog (`app/packs/`:
  self-monitoring, service heartbeat, sensor threshold, Alertmanager), the
  `/v1/packs` API (list, inspect, preview, apply — audited as
  `pack.install`) and an admin-UI **Packs** page: fill in the settings,
  review every item (new / identical / different, overwrite / skip / copy),
  install. Any selection exports as a pack (`pack_id` on
  `/v1/config/export`), with dependencies closed over inputs, computed
  variables, inhibiting rules, gate variables and route channels. The
  built-in self-monitoring templates now come from their pack. Replaces the
  `examples/` directory.
- `scripts/deploy.sh --runtime-dir=DIR` (or `KLOPOT_RUNTIME_DIR`) builds the
  image from the checkout and recreates the service from a separate runtime
  directory that holds `.env` and the compose files; `ALERTD_MYSQL_CONTAINER`
  names an external database container for the backup.
- Conditional fields in `/v1/meta/kinds` (`show_if`): the admin UI shows only
  the fields of the chosen variant (e.g. the SMS provider) and does not save
  hidden ones.

### Changed

- `push` channel: devices live in `push_subscriptions` (no longer
  `user_prefs.settings.push_subscriptions`, which nothing ever wrote);
  `vapid_public` is gone from the config (derived from the private key); a
  missing or invalid key fails the delivery permanently instead of retrying.
- Delivery semantics an upstream can ask for: adapters report backpressure
  (`Retry-After` on 429 / 503) and permanent refusals (4xx such as 422).
  Backpressure defers the delivery by exactly that long without spending an
  attempt or tripping the breaker; a permanent refusal fails at once. The SMS
  `http` provider and the webhook expose `{idempotency_key}` (stable across
  retries) to the body template; the SMS `http` provider takes
  `success_statuses` (e.g. `[409]` for a gateway's "duplicate, already sent").
- Secrets in one step: any `KLOPOT_SECRET_<NAME>` variable may be used as a
  `*_ref` without an allowlist entry, and `docker-compose.yml` loads an
  optional `secrets.env` (see `secrets.env.example`) into the app only.
  Before, a token for a new channel or pack needed `.env` + the compose
  `environment:` list + `ALERTD_SECRET_REF_ALLOW`. The pack preview says
  whether each secret a pack needs is set; the `alertmanager` pack's token
  defaults to `KLOPOT_SECRET_ALERTMANAGER_TOKEN`.
- Every channel test is a new message (its own id and idempotency key): a
  gateway that deduplicates on the key replayed a second test within its
  window, so the UI said "sent" while nothing went out.
- Tapping a channel-test notification (ntfy, Gotify, Pushover) opens the
  Channels page; it opened a log entry that does not exist.
- A channel test now reads "Test from Klopot (<channel>)" — "If you can read
  this, the channel works…" — with type `channel_test` (was `alertd_test`,
  "…triggered manually via the API" even when sent from the UI). Email
  notifications are signed "— Klopot".
- Removed the energy-specific `| kw` template filter; `{p | div(1000) |
  fixed(1)}` gives the same text. The admin-UI preview now supports exactly
  the server's filters (it lacked `json` and `jsonstr`). Filters are
  documented in `docs/EXPRESSION_LANGUAGE.md`.
- Examples in the admin UI (English and Romanian), help texts and docs are
  generic (disk, temperature, tank) instead of one deployment's solar and
  battery setup.
- **Delivery gate is generic** (migration `0030`): a template names its own
  `gate_variable` and `gate_min` and is suppressed as `below_gate` while the
  variable is below the minimum (fail-open on a missing or stale value).
  This replaces the solar-specific `require_pv_kw` + global
  `ALERTD_PV_POWER_VAR`; existing values are converted. On `/v1`
  `require_pv_kw` stays a deprecated alias of `gate_min` (read and write),
  and config import still accepts it with a warning.
- Admin UI on a phone: one compact sticky bar (logo, health, menu); language,
  theme, account and sign-out move into the menu, so the page title is no
  longer hidden and the menu button is always reachable. Controls have
  44 px touch targets.
- Admin UI: severities, health statuses and components, suppression reasons
  and relative times are translated (Romanian showed "-9 m" and English
  terms); form mistakes are marked on the field with an error summary
  instead of a toast; toasts are cleared when you change page; the
  dashboard lists unacknowledged criticals so long titles wrap and Ack stays
  visible.
- Accessibility: rows and buttons keep their visible text as the accessible
  name (WCAG 2.5.3), drawers use a valid dialog element, empty table headers
  are named, the login and password screens have a main landmark and a
  heading, and the dark `--crit` colour passes 4.5:1 on every theme surface
  (ADR-0001 amended).
- Documentation distinguishes the 1.0.1 release, later implementations and
  deployment configuration, and clarifies MySQL runtime versus SQLite tests.
- Config import stores a template category with the spelling already in use,
  like the API.
- Template icons must be an emoji: text and mis-encoded values (`âš¡`, `??`)
  are rejected on create, update and import. A category that differs from an
  existing one only by case reuses the existing spelling.
- `has_error=true` on `GET /v1/rules` now means `eval_status=error`; a rule
  only waiting for an input is no longer counted as an error.
- `/docs`, `/redoc` and `/openapi.json` are now available to any authenticated
  caller (admin session or `X-API-Key`) on a production/TLS deploy instead of
  being switched off; anonymous callers get 401 (schema) or a redirect to the
  admin login (HTML). `ALERTD_DOCS_ENABLED=true` still makes them public.

### Fixed

- A snooze `reason` longer than the database column (64 KiB on MySQL)
  answered 500; it is now limited to 500 characters (422 beyond).
- A rule (without incidents) that went false and true again within five
  minutes with the same values was merged into its previous notification
  with no trace. Such a re-occurrence is now logged as a suppressed
  `duplicate` row (still not sent twice); a rule that stays true adds no rows.
- `backup.sh` removes the uncompressed partial file a killed run left behind
  (older than six hours); rotation never matched it, so each one stayed.
- Performance (MySQL): the hourly retention deleted from `login_attempts`,
  `admin_sessions` and `inbound_events` without a usable index, scanning and
  locking the whole table for the rest of its transaction. Migration `0039`
  adds the indexes. The model now names the `incidents.source_key` index as
  migration `0028` created it.
- Backup sidecar: the schedule loop used a bash-only construct (it worked
  only because the image's `/bin/sh` is bash) and a step value such as
  `*/15` in `BACKUP_CRON` stopped it. The loop is now POSIX sh in
  `scripts/backup_scheduler.sh`, accepts `*`, `N` and `*/N`, refuses anything
  else at start, and is tested.
- A hand-made `ALERTD_BOOTSTRAP_ADMIN_KEY` in the shape of a generated key
  (`alertd_` + 43 characters) got the fast SHA-256 lookup meant for random
  keys, cheap to reverse from a leaked table if the key is weak. The seed now
  refuses such a key when it is visibly not random; generate it as
  `.env.example` shows.
- Egress: the email channel connects to the address its host was screened
  for (a DNS answer that changed between the check and the connection could
  reach a forbidden host); TLS still verifies the configured name. MQTT
  brokers (channel and input) are no longer contacted at a metadata,
  link-local, multicast or unspecified address (private brokers are fine).
  Alibaba Cloud's metadata address `100.100.100.200` is always refused, not
  only under strict egress.
- A failed or blocked sign-in recorded the typed username in the audit log,
  which `read` keys can list — a password typed into the username field
  became readable. The audit now names only an existing account; anything
  else is recorded as `unknown:<short digest>`.
- Admin UI, Log with live tail: after the live connection dropped and came
  back, the badge said live but alerts fired meanwhile were missing until the
  next one arrived. The list is now refreshed (or flagged as having new
  rows) when the connection returns.
- Admin UI template preview: it rendered `%name%` placeholders in a second
  pass (a value containing `%x%` was expanded again, unlike the real alert),
  showed inherited properties for `{constructor}`-like names, and a
  placeholder such as `{__proto__.x}` could write to `Object.prototype` in
  the page. It now renders in one pass like the server and reads own values
  only.
- Expressions: a control character in an expression made validation and
  evaluation fail with a server error (500 from `POST /v1/rules/validate`)
  instead of a message, and a triple-quoted string holding a quote had the
  `AND` / `OR` / `NOT` inside it rewritten, so the rule compared against
  different text. Both are now refused with a message.
- An aggregate variable whose sum or average overflowed (two 1e308 readings)
  became infinity, which `/v1/state` could not encode (500) and the admin UI's
  live view could not parse; it is now `null`, like a non-finite reading. An
  MQTT `payload_template` containing `NaN` / `Infinity` publishes `null`
  instead of invalid JSON.
- `deploy.sh` and `restore_drill.sh` checked a fixed port 5090: on an install
  with another `KLOPOT_HTTP_PORT`, a different service answering there made a
  failed deploy look healthy. All three scripts now take the port from
  `.env` (`scripts/_klopot_url.sh`).
- A scheduled notification could be skipped while the service was running
  ("overdue … was the service down?"): a slow tick or a retry after a database
  error made it more than a minute late. Only occurrences that fell due
  before the service started are skipped now; a late one is still sent.
- A notification could stay `pending` for good although every channel had
  settled, when an incident was resolved while one of its channels was being
  retried (each side wrote the status from an older snapshot, MySQL). It was
  shown as in flight and an identical alert within five minutes was merged
  into it and not sent. The delivery worker now corrects such rows on every
  tick.
- Wrong-API-key budget: a burst of concurrent wrong keys from one address
  now gets 5 hashes (each attempt is counted before hashing, given back if
  the key is right); an IPv6 client counts by its /64; the WebSocket
  `?api_key=` path counts the real client behind the proxy, not the proxy;
  making room past 10,000 addresses no longer rebuilds them all on the event
  loop; and with every `X-Forwarded-For` hop trusted the TCP peer is used,
  never the client's own leftmost claim.
- Performance (MySQL): the duplicate check of every fire filtered
  `is_test IS false`, which MySQL does not use as a key equality, so it
  scanned every recent notification of the type instead of one key lookup.
- Pushover: an acknowledgement made in the Pushover app could stop reaching
  Klopot (and the SMS escalation still went out): with 50 receipts of the last
  three hours already acknowledged or closed, newer ones were never polled.
  The poll now selects only open receipts, through a new index on
  `deliveries.provider_ref` (migration `0038`) instead of scanning the
  delivery history every minute.
- An external episode whose first firing was muted is no longer announced
  after someone acknowledged it, and two repeats arriving at once (two
  Alertmanager replicas, or a fast source) no longer both announce it on
  MySQL: the "was it announced?" check reads the current state, not the
  transaction's older snapshot.
- Web Push: who paused a device is now recorded (`paused_reason`, migration
  `0037`) instead of guessed from its failure count. Re-registering an
  auto-paused device enables it again (it used to stay paused with a clean
  count, and alerts were logged as sent to 0 devices); a device the operator
  keeps paused no longer makes every push alert fail; a 401/403 from every
  device (our VAPID key refused) no longer pauses them all. The device list
  says when the service paused a device.
- The inbound webhook endpoint (`POST /v1/inputs/{id}/webhook`, anonymous)
  named the input and its kind (400) or said its adapter was not running
  (503) before checking the token, so inputs could be enumerated; and those
  answers, a 413 or a 422 kept up to 64 KiB of the anonymous body in the
  Activity log. Anything that is not a webhook-kind input now answers a
  generic 404, the token is checked next, and a body is kept only for a
  caller the endpoint let in.
- An ntfy channel's `topic` was returned to any `read` key, though on ntfy the
  topic name is the credential (whoever knows it can subscribe and publish).
  It is now write-only like the token, may come from `topic_ref`, and is
  masked in exports, the audit log and stored Activity bodies (any `topic`
  key there is masked).
- An upstream that echoed the request in its error (`Cannot POST
  /services/T0/…` on a 404, a gateway quoting the token it refused) put the
  webhook path or the credential into the delivery error, the log's failed
  channels and the Activity log, readable with `read` scope while the channel
  config itself is masked. Every stored error now has the channel's secret
  values (literal, from `*_ref`, custom header values) and the path, query and
  password of its URLs replaced by `***`.
- A failed outbound request no longer stores the text of an HTTP protocol or
  URL error, which can quote a header or the URL it was given (a bearer
  token, a webhook path): delivery errors and the Activity log keep its type
  (`LocalProtocolError`). Connection, timeout and read/write errors keep their
  message, with URLs reduced to `scheme://host/…`.
- A secret with a trailing space, CR or newline (a `secrets.env` line, a
  quoted `\n`) made the HTTP library refuse the request and quote the header,
  token included, in an error stored on the delivery and in the Activity log.
  Resolved secrets are now trimmed, and one with a control character inside
  is refused (the send fails as a missing secret; the log names the variable,
  never the value).
- A burst of anonymous sign-ins could starve alerting: each login kept its
  database connection while it waited for a password-hashing slot, and the
  wait had no limit, so about fifteen concurrent wrong logins held the whole
  pool. The connection is now returned before hashing, and past 16 waiting
  sign-ins the answer is 503 with `Retry-After`.
- A channel whose breaker was letting its single trial send through could stay
  blocked for good: when that first attempt ran past its time budget and was
  cancelled, the trial was never given back, so every later message was
  deferred as `circuit_open` until a restart or a manual breaker reset. A
  cancelled dispatch now releases the trials it held.
- Acknowledging a notification while the delivery worker was settling one of
  its channels deadlocked on MySQL (error 1213): the acknowledgement answered
  500, or the worker lost the record of a send it had made and sent it again.
  The acknowledgement no longer waits for delivery rows a worker holds.
- Expressions could hold the event loop for seconds within the length and
  node limits — through `POST /v1/rules/validate` with a `read` key, or in a
  stored rule on every tick: `sum()` concatenated lists in one call,
  `round(5, -9999999)` computed a ten-million-digit power, and many products
  that each passed the per-operation cap added up. `sum()` now takes numbers
  only, `round()` takes `n` between -100 and 100, and one evaluation may build
  at most 1,000,000 elements or characters through `*` and `+`.
- Template rendering could block the service: the output cap was applied only
  after the whole result was built (a placeholder repeated over a large value
  allocated gigabytes), and the preview found unresolved names with a regex
  over the output that a crafted value made quadratic (a `read` key could
  hold the event loop for minutes). The cap now applies while rendering and
  unresolved names are collected during substitution, so a value that
  contains `[?x]` is no longer reported as a missing variable.
- A lone UTF-16 surrogate in a payload (`"\ud800"` is valid JSON) made the
  database refuse the notification, so `/v1/fire` answered 500 and an alert
  built from such a variable was lost on every cycle. It is now replaced by
  U+FFFD in the type, source, context, episode name and stored payloads.
- A rendered message longer than 65,535 bytes (a long log excerpt or
  Alertmanager description; 32 K diacritics are enough) was refused by MySQL
  and the alert was lost on every retry. It is now cut to fit, on a character
  boundary, ending in `…`.
- External episodes on MySQL: `idempotency_key` values that differ only in
  case (`DiskFull`, `diskfull`) were one episode — the second firing sent
  nothing and resolving one closed the other. The episode key columns now
  compare byte for byte (migration `0036`).
- Parallel `/v1/fire` calls of one template type with different contexts no
  longer deadlock on MySQL (error 1213, HTTP 500, alert not stored): the
  dedup-claim read-back is a primary-key point read again.
- Activity log, secrets: a delivery attempt keeps only `scheme://host/…` of
  the destination (a webhook path can be the credential) — also for rows
  stored earlier, at read time; form bodies (Pushover app token and user
  key) and every value under `headers` are masked; `/v1/auth/*` responses
  and `/v1/config/*`, `/v1/packs/*` request bodies are never stored.
  **After upgrading, rotate credentials that were in use with the Activity
  log enabled** (Pushover token and user key, webhook URLs with a secret
  path): rows written before the upgrade still hold them until they expire.
- Every send looked its delivery rows up by `idempotency_key`, which had no
  index: a full scan of `deliveries` per send, so a fire took ~0.1 s on a
  small table and ~0.9 s at 1.4 million rows. Schema 0035 adds the index.
- `scripts/backup.sh` no longer passes a failed dump off as a backup: with
  `mysqldump | gzip` a dump that failed (server down, wrong password, full
  disk) left a 20-byte `.sql.gz`, logged "backup done" and exited 0 while
  rotation kept deleting the good ones. A failed or incomplete dump now
  exits non-zero and leaves no file. **Check your `backups/` for files of
  a few dozen bytes.**
- `scripts/restore_drill.sh` waited for MySQL with `mysqladmin ping`, which
  answers before the root password exists, so every drill failed with
  "dump may be corrupt"; it now waits for a real query, reports the actual
  restore error, and recognises the revision of recent migrations.
- `scripts/bootstrap.sh` waits on the port from `KLOPOT_HTTP_PORT` instead
  of a fixed 5090 (where it reported the health of whatever else listened
  there) and on `/v1/health/ready`.
- External episodes (Alertmanager, `/v1/fire` with an `idempotency_key`):
  an alert whose first firing was snoozed, in quiet hours, throttled or
  failed on every channel is announced by a later firing once nothing mutes
  it. Before, every later firing was a `repeat` and the alert stayed silent
  for as long as it lasted. An episode that was announced still notifies
  once.
- A `json` variable (or a `/v1/fire` context) containing `NaN` or
  `Infinity` no longer makes MySQL reject the notification — every fire
  carrying it failed on each cycle with only a log line. Non-finite numbers
  are stored and rendered as empty (`null`).
- `POST /v1/fire` with the longest valid API-key name and `idempotency_key`
  (198 characters together) no longer answers 500 on MySQL: an episode key
  longer than its column keeps its head plus a digest. The same applies to
  an Alertmanager fingerprint of any length.
- Web Push: a send that never reached the push service (timeout, connection
  or DNS failure) no longer counts toward the 20-failure pause — a network
  outage on the server paused every device and nothing re-enabled them. An
  alert whose only recipients are devices the service paused now fails
  visibly instead of being logged as sent to 0 devices. **Check Devices
  after upgrading:** devices paused by an earlier outage stay paused until
  re-enabled.
- API keys are found by an indexed SHA-256 digest (schema 0034,
  `api_keys.key_digest`): a wrong key costs one indexed read and no bcrypt,
  and a right key no longer waits behind wrong ones. Keys issued earlier get
  their digest on first use; an operator-chosen key (the bootstrap key)
  keeps bcrypt only.
- Wrong API keys can no longer stall the service: an address gets 5 wrong
  keys a minute (then `429`), the verification queue is capped (`503` +
  `Retry-After`), and no database connection is held while a key is hashed.
  `api_keys.last_used_ip` is now the real client address behind a trusted
  proxy.
- Activity log: the request body of a caller who was not authenticated (or
  whom an inbound endpoint refused) is never stored; an anonymous client
  could make the service keep 4 KiB — 64 KiB on an inbound endpoint — per
  request.
- A `422` no longer echoes the rejected value (`input`): a body sent with
  the wrong content type was echoed whole, secrets included.
- Activity events: a rule without data for a tick ("missing input", e.g.
  right after a restart) no longer writes an `eval_error` / `eval_recovered`
  pair; only real evaluation errors are events.
- Admin UI: the Activity filters keep the "Webhooks only" checkbox next to
  its label, the tabs scroll sideways on a phone instead of wrapping, the
  dashboard's Refresh stays beside the title on a phone, suppression reasons
  are no longer Title Cased, every pack card has Install bottom-right, and
  activity rules are numbered 1, 2 … with a correct plural ("keep 1 day",
  "păstrează 90 de zile").
- Admin-UI focus tests wait for the next frame instead of a fixed delay, so
  they no longer fail intermittently on a loaded run.
- A rotated API key's name carries 32 random bits instead of 16, so many
  rotations of one key in the same second no longer risk a name clash.
- A rule's "missing input" message stayed on the rule after the input came
  back, so healthy rules were shown as failing. A successful evaluation now
  clears it, and an unchanged message is no longer rewritten every tick.

## [1.0.1] — 2026-11-14

Deployment and validation evidence for this baseline is recorded in
[project status](docs/PROJECT_STATUS.md#validation).

### Added

- Operational monitoring page and `GET /v1/operations` (read scope), with
  durable queue counts/age, active-lease-aware overdue checks, worker liveness,
  Telegram/MQTT connections and recent terminal failures. Prometheus metrics,
  a portable Grafana dashboard and eight example alert rules ship in `contrib/`.
- Native MQTT output with persistent/reconnecting connections, verified TLS,
  QoS 0/1/2, retain off by default, JSON payload templates and stable delivery
  identities. Per-output availability/LWT and process/engine heartbeat topics.
  Migration `0027` preserves existing channels.
- Opt-in Telegram acknowledgement and snooze buttons, actor allowlists,
  dedicated-bot long polling, durable callback processing and independent
  keyboard cleanup retries. Migration `0026`; setup: `docs/TELEGRAM.md`.
- Channel delivery details in `GET /v1/log/{id}` and the admin log drawer
  (English/Romanian): purpose, state, attempts, next scheduled attempt,
  active reservation and last error, with manual refresh.
- Optional rule incidents with persistent active/resolved state, independent
  acknowledgement, hysteresis/recovery confirmation and configurable recovery
  notices. Resolution cancels queued alarms and escalation.
- Incident API and admin page (English/Romanian), related notification history,
  manual resolution with reason, and lifecycle fields in rule config/import/export.
  Migration `0025` preserves existing rules, counters and notifications.

### Changed

- Escalations are persisted before sending and retried by the outbox worker,
  up to five transport attempts and a one-hour queue lifetime. Acknowledgement
  cancels queued escalations. Initial delivery status and counters remain
  independent. Migration `0024` preserves existing deliveries and allows the
  initial notification and its escalation to use the same channel.

### Fixed

- Docker build context excludes all local `.env.*` variants, while retaining
  the committed `.env.example` template.

## [1.0.0] — 2026-11-13

First public release. Klopot grew out of the alerting service of a private
home-energy deployment, where it ran in production through many internal
iterations; that history is not carried over.

### Added

- **API-first configuration.** Inputs, variables, rules, templates, channels,
  routing and schedules are database rows, managed over a versioned REST API
  (`/v1/`) with a live OpenAPI document at `/docs`. Config export, validate
  and import as YAML or JSON (`/v1/config/*`).
- **Fire API.** `POST /v1/fire` lets any HTTP client raise an alert by type,
  with an idempotency window and API keys scoped `fire` / `read` / `ack` /
  `admin`.
- **Inputs:** MQTT, HTTP polling, token-gated inbound webhooks and an SMS
  inbox.
- **Channels:** Telegram, email (SMTP), SMS via an HTTP gateway, generic
  webhooks (with presets such as ntfy), Web Push (VAPID), and the in-app
  UI/banner channel. Per-channel circuit breaker and rate limiting.
- **Rules engine.** A sandboxed, whitelisted expression language (no raw
  `eval`), N-of-N persistence, per-rule evaluation interval, computed and
  aggregate variables, and Alertmanager-style inhibition.
- **Gating.** Enable flags, snooze (by type, rule or channel), quiet hours,
  minimum-repeat throttling, duplicate coalescing, escalation of
  unacknowledged critical alerts, and a daily digest of suppressed alerts.
- **Durable, at-least-once delivery.** Each fire is persisted with a delivery
  row per channel before any external send; a background worker retries with
  backoff and reconciles after a restart.
- **Admin UI** at `/admin`: a build-less Preact single-page app to manage
  everything, watch the live notification log over WebSocket and test
  channels. Session login with lockout, CSRF protection and a strict
  Content-Security-Policy; keyboard-accessible with WCAG AA contrast;
  English and Romanian; light/dark Klopot theme plus optional OS-native theme
  families.
- **Security hardening.** SSRF screening and IP pinning on every outbound
  HTTP call, environment-variable references for secrets and write-only literal
  credentials, credential redaction in logs and API output, request size
  caps, and ReDoS-safe regular expressions.
- **Observability.** Structured JSON logs, Prometheus metrics at
  `/v1/metrics`, request trace ids, readiness/liveness health endpoints and an
  audit log of every configuration change.
- **Deployment.** Docker image, MySQL 8 with Alembic migrations applied on
  startup, a backup sidecar, and three compose variants — production,
  production behind traefik (docker or file provider), and development — plus
  a self-contained two-minute demo (`compose.demo.yml`).
- **Examples.** Importable config packs in `examples/` (uptime monitoring and
  an IoT threshold alert).

[Unreleased]: https://github.com/sm26449/klopot/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/sm26449/klopot/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/sm26449/klopot/releases/tag/v1.1.0
