# Activity log — design

Status: **implemented** 2026-11-14 (migration 0032). Owner's decisions: record everything, decide what to keep with rules editable from the UI, retention = `log_retention_days`.

## Why

Klopot records *what* happened to an alert (`notifications_log`, `deliveries`)
and *who changed the configuration* (`audit_log`), but not *how the
conversation with the outside world went*:

- A delivery keeps only `last_error` (500 characters), overwritten by every
  retry — the history of attempts is lost. The 2026-11-13 burst of 429s from
  the SMS gateway was visible only in the gateway's database.
- An API request that fails (wrong key → 401, bad body → 422, rate limit →
  429) leaves no trace outside the container's stdout, which is lost on
  rotation and on every recreate.
- Inbound webhook / Alertmanager payloads are never stored, so an ignored or
  odd alert cannot be inspected afterwards.
- Input connect / disconnect / error and rule evaluation errors keep only the
  latest state.

## What is recorded

### 1. Delivery attempts — `delivery_attempts`

One row per attempt to a provider (alerts, escalations, retries, channel
tests). Answers "why did — or didn't — this message arrive?".

| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGINT PK | |
| `delivery_id` | BIGINT NULL FK → deliveries (CASCADE) | NULL for a channel test |
| `notification_id` | VARCHAR(64) NULL | for the Log drawer timeline |
| `channel` | VARCHAR(64) | |
| `kind` | VARCHAR(16) | `alert`, `escalation`, `test` |
| `attempt_no` | INT | 1-based, per delivery |
| `started_at` | DATETIME | |
| `duration_ms` | INT | |
| `outcome` | ENUM | `sent`, `failed`, `deferred` (Retry-After / breaker / rate limit), `permanent`, `timeout` |
| `http_status` | SMALLINT NULL | last HTTP status of the attempt |
| `retry_after_sec` | INT NULL | what the provider asked for |
| `provider_ref` | VARCHAR(255) NULL | |
| `error` | VARCHAR(500) NULL | redacted |
| `exchange` | JSON NULL | the HTTP exchange(s) — see below |

`exchange` is a list (an attempt can make several requests: Teltonika logs in
then sends; several SMS recipients): per request `method`, `url` (host only,
`https://host/…` — a destination path can itself be the credential), `status`, `duration_ms`, `request_body`,
`response_body` (each trimmed to 4 KB, redacted), and only these response
headers: `Content-Type`, `Retry-After`, `Idempotent-Replayed`.

**How it is captured:** a recorder (a context variable) is opened around each
`adapter.send()`; `safe_request` and the Telegram client append every
exchange to it. No adapter code changes for HTTP providers. Email (SMTP) and
MQTT record the outcome and their server reply / error without an exchange.

### 2. API requests — `api_requests`

| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGINT PK | |
| `ts` | DATETIME | |
| `method`, `route`, `path` | | `route` is the template (`/v1/inputs/{input_id}/webhook`) — for grouping |
| `status` | SMALLINT | |
| `duration_ms` | INT | |
| `actor_kind`, `actor_name`, `api_key_id` | | key name or admin user; NULL if anonymous |
| `client_ip`, `user_agent`, `trace_id` | | `trace_id` = the `X-Trace-Id` in the logs |
| `request_body` | MEDIUMTEXT NULL | see policy |
| `response_body` | TEXT NULL | only when `status >= 400`, 2 KB |

**Policy.** Every request under the app is recorded (admin-UI static files
excepted) — "see everything that arrives and from where". What is kept of it
is decided by **activity rules** (next section); without a matching rule:

| Request | Kept for | Request body | Response body |
|---------|----------|--------------|---------------|
| `POST /v1/fire` | `log_retention_days` | yes, 4 KB | yes, 2 KB |
| Inbound webhook / Alertmanager / SMS inbox (`POST /v1/inputs/{id}/webhook`) | `log_retention_days` | yes, **64 KB** — the raw payload archive | yes, 2 KB |
| Other writes | `log_retention_days` | on error only | on error only |
| Reads (`GET`) | `log_retention_days` | — | on error only |
| `/v1/auth/*` | `log_retention_days` | **never** (passwords) | **never** |
| `/v1/config/*`, `/v1/packs/*` | `log_retention_days` | **never** (whole configurations, literal secrets included) | on error only |

A fresh install has two preset rules — health probes (`/v1/health*`) and the
Prometheus scrape (`/v1/metrics*`) are kept **one day** without bodies — so
they stay visible without piling up. Edit or delete them like any rule.

### Activity rules — `activity_rules`

Edited in the admin UI (Activity → Rules) or `/v1/activity/rules`. The first
enabled rule (lowest `position`) that matches decides:

| Match on | Example |
|----------|---------|
| method | `GET` (empty = any) |
| path (glob) | `/v1/health*`, `/v1/inputs/*/webhook` |
| status | `4xx`, `5xx`, `401` (empty = any) |
| key / user (glob) | `backup-script*` |
| client IP (glob) | `10.0.0.*` |

| Action | Effect |
|--------|--------|
| `keep` | stored; `keep_days` shortens retention (1 = deleted after a day), and `request_body` / `response_body` = `auto` (the table above), `never`, `errors`, `always` |
| `ignore` | **not stored, only counted**: the rule keeps `hits`, `last_hit_at` and `last_ip`, shown under Activity → Sources, so you still know such requests arrive |

The UI previews a rule against the last 24 h ("would match N of the last M
requests") before you save it, and Sources offers "Rule…" on any row.

### Sources

`GET /v1/activity/sources?hours=24` groups the stored requests by key / user,
client IP, method and route, with counts per status class and the last time
seen — plus the counters of every `ignore` rule. It answers "who calls
Klopot, from where, and how does it go?".

### 3. Raw webhook payloads

Not a separate table: the webhook rows of `api_requests` (64 KB bodies) are
the payload archive. The input editor gets a "Recent payloads" panel; the
Activity page a "Webhooks" tab.

### 4. System events — `system_events`

Written **only on state changes**, never per tick or per message.
A rule with no data for a tick ("missing input") is not an error and
writes no event; only real evaluation errors open an `eval_error`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGINT PK | |
| `ts` | DATETIME | |
| `source_kind` | VARCHAR(16) | `input`, `rule`, `channel`, `push_device` |
| `source_id`, `source_name` | | |
| `event` | VARCHAR(32) | input `connected` / `disconnected` / `error` / `recovered`; rule `eval_error` / `eval_recovered` / `auto_disabled`; channel `breaker_open` / `breaker_closed`; push_device `device_removed` (the push service said gone) / `device_disabled` (20 failures in a row) |
| `detail` | VARCHAR(500) NULL | redacted error text |

## What is never stored

- Request or response **headers**, except the three response headers listed
  above (so never `Authorization`, `X-API-Key`, `X-Input-Token`, cookies).
- The request body of a caller who did not get in: any request without a
  valid API key or session, and any request to an inbound endpoint
  (`/v1/inputs/{id}/webhook`) that the endpoint did not let in — whatever it
  answered (401, 404, 413, 422 …). No activity rule can turn this on.
- The request and response bodies of `/v1/auth/*`, and the request body of
  `/v1/config/*` and `/v1/packs/*` (an import can carry literal secrets, and
  YAML is not masked key by key).
- The path and query of a destination URL: an exchange keeps
  `scheme://host/…`, in its `url` and in its `error` text.
- The value a validation error complains about: a `422` names the location
  and the problem, never the `input`.
- Secret values in bodies: JSON keys matching the secret registry
  (`password`, `token`, `api_key`, `secret`, `auth_value`, `bot_token`,
  `user_key`, …) and every value under `headers` are replaced by
  `<redacted>`; form bodies (Pushover) are masked field by field; URLs go
  through `redact_url`.
- MQTT message values (volume; the state cache and `/v1/state` already show
  the latest value per variable).

`ALERTD_ACTIVITY_LOG_BODIES=false` keeps every row but drops all bodies, for
deployments that must not store message content.

## Writing — off the hot path

Rows go into a bounded in-memory queue; a background writer inserts them in
batches (every second or every 100 rows) in its own transaction. Recording
never blocks or fails a request or a send: a full queue drops the row and
counts it (`klopot_activity_dropped_total`). A crash loses at most the
unwritten second.

## Retention

The existing retention task sweeps the three tables with
`log_retention_days` (default 90), in batches, like `notifications_log`.

## Access

| Endpoint | Scope | Returns |
|----------|-------|---------|
| `GET /v1/activity/sources` | read | grouped callers + ignored counters |
| `GET/POST/PATCH/DELETE /v1/activity/rules`, `POST /v1/activity/rules/preview` | read (list, preview) / admin (changes, audited) | the rules |
| `GET /v1/activity/requests` | read | rows without bodies; filters: status class, route, actor, method, since/until, trace id |
| `GET /v1/activity/requests/{id}` | **admin** | with bodies |
| `GET /v1/activity/events` | read | filters: source kind / id, event, since/until |
| `GET /v1/activity/attempts?notification_id=…` / `?channel=…` | read (bodies: admin) | attempts of one notification (in order) or one channel |

Bodies need `admin` because alert text and payloads can carry personal data
(phone numbers, hostnames); metadata is enough for `read`.

## UI

- **Activity** page (System group): tabs **Requests** (with a "webhooks
  only" filter — the payload archive), **Sources**, **Deliveries**,
  **Events**, **Rules**; filters in the URL; a request opens a drawer with
  its bodies.
- **Log drawer**: an "Attempts" timeline — e.g. `429 · waited 240 s → 200 sent`.
- **Channel editor**: the last attempts and tests of the channel.
- **Input editor**: recent payloads (webhook inputs) and events.

## Migration

`0032_activity_log`: the four tables (incl. `activity_rules` with the two preset rules) with indexes on (`ts`), (`route`,
`ts`), (`status`, `ts`), (`delivery_id`), (`notification_id`), (`channel`,
`started_at`), (`source_kind`, `source_id`, `ts`). Forward-only, additive.
