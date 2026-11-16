# alertd — API Reference

**Languages:** **English** · [Română](API.ro.md) ·
[← Back to README](../README.md)

Everything in alertd is driven by this HTTP API. Every running instance
serves the live reference: **API reference** in the admin UI (each endpoint
with its required scope and a curl example), **Swagger UI** at **`/docs`**,
ReDoc at `/redoc` and the raw schema at **`/openapi.json`** (each operation
carries `x-required-scope`). On a production/TLS deploy these are served only
to a logged-in admin session or a request with a valid `X-API-Key`
(`ALERTD_DOCS_ENABLED=true` makes them public). This document is the
hand-written companion with concepts and examples.

- **Base URL:** `http(s)://<host>:5090` (behind a reverse proxy in
  production, e.g. `https://alerts.example.com`).
- **Versioning:** every route is under **`/v1`**. Breaking changes go to
  `/v2`.
- **Content type:** JSON, except config import/export (YAML).

---

## Authentication

Two mechanisms, both resolving to an **actor** with a set of **scopes**:

### 1. API key (machine-to-machine)

Send the key in the `X-API-Key` header. This is what scripts, Node-RED,
and other services use.

```bash
curl -H "X-API-Key: alertd_xxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
     https://host/v1/log?limit=5
```

Keys are created via [`POST /v1/api_keys`](#api-keys) (admin scope) and
returned **once** in plaintext. Store them as a secret. Keys can carry
an `expires_at` and be disabled/rotated; revocation takes effect
immediately.

### 2. Browser session (admin UI)

The admin UI at `/admin` logs in with `POST /v1/auth/login`
(username + password), which sets an `alertd_session` cookie and an
`alertd_csrf` cookie. **Unsafe methods** (POST/PATCH/PUT/DELETE) from a
cookie session require the CSRF token echoed back in the
`X-CSRF-Token` header. API-key callers don't need CSRF.

### Scopes

| Scope   | Grants |
|---------|--------|
| `read`  | Read endpoints (log, state, config export, lists) |
| `fire`  | `POST /v1/fire` |
| `ack`   | `POST /v1/log/{id}/ack`, `POST /v1/incidents/{id}/ack` / `resolve`, `POST /v1/snooze`, `DELETE /v1/snooze/{id}` |
| `admin` | Everything (implies all other scopes) |

Scopes are additive on a key (e.g. `["fire", "read", "ack"]`). `admin`
implies every scope. A few reads are admin-only (`GET /v1/api_keys`,
`GET /v1/config/export`, `GET /v1/activity/requests/{id}`); the exact scope
of every operation is its `x-required-scope` in `/openapi.json`. A `401` means "not authenticated"; a `403` means
"authenticated but missing the required scope". Wrong keys are bounded: after 5 of them within a minute from
one address the next ones get `429` with `Retry-After: 60` (a key that already verified keeps working), and a
`503` with `Retry-After: 1` means too many keys are waiting to be verified — retry.

---

## Error model

Errors are JSON. Handled errors use FastAPI's `detail`; a structured
error carries a `code`/`message`. Unexpected server errors return a
generic body plus an `X-Trace-Id` header for correlation (no internal
details are leaked). A `409` on a duplicate name currently includes the
database's own message (the constraint name); treat `detail` as text for
people, not as a contract. A `422` lists where each problem is (`loc`, `msg`,
`type`) and never echoes the rejected value.

```json
{ "detail": "Variable not found: disk.used_pct" }
```
```json
{ "detail": { "code": "INVALID_CREDENTIALS", "message": "Invalid username or password" } }
```

Validation errors (`422`) list the offending fields:

```json
{ "detail": [ { "loc": ["body", "type"], "msg": "Field required", "type": "missing" } ] }
```

## Conventions

- **Pagination:** list endpoints take `skip` (offset) and `limit`
  (default 50 — 100 for `/v1/variables` — max 500) and return `{ "items": [...], "total": N,
  "limit": L, "offset": O }`.
- **Timestamps:** ISO-8601 UTC.
- **Identifiers across config:** names/types (strings), not DB ids, so a
  config pack is portable between deployments.

---

## Health & version

```bash
curl https://host/v1/health      # service + DB + MQTT + per-channel/input
curl https://host/v1/health/ready   # same body; 503 when an essential component is down
curl https://host/v1/version     # version string only, no infra probes
```

`/v1/health` (public) always answers 200 with an overall `status` (`ok` /
`degraded` / `down`), a `components` map and `docs_enabled`.
`/v1/health/ready` returns the same body but with HTTP 503 on an essential
outage — use it as a readiness probe. Use `/v1/version` for a cheap liveness
probe that never touches MySQL/MQTT.

```json
{ "status": "ok", "service": "alertd", "version": "1.7.0", "docs_enabled": false,
  "components": { "database": {"status":"ok"}, "mqtt": {"status":"ok","detail":"critical: 1/1 connected"} } }
```

## Metrics

`GET /v1/operations` requires `read` scope and returns `queues`, `workers`,
`telegram`, `mqtt` and `recent_failures`. It is read-only and excludes raw
callbacks, action capabilities and credentials. [Operational reference](OPERATIONS.md).

```bash
curl -H "X-API-Key: $KEY" https://host/v1/metrics     # Prometheus exposition format
```

`/v1/metrics` needs a `read` key when `ALERTD_METRICS_REQUIRE_AUTH` is true
(default: on when `ALERTD_COOKIE_SECURE` is true), otherwise it is public.
Exposes `alertd_fires_total`, `alertd_dispatch_latency_ms`,
`alertd_dispatch_failures_total`, `alertd_rule_eval_duration_ms`, queue-age
gauges, `klopot_activity_dropped_total`, and more.

---

## Fire a notification

The one endpoint every external caller needs. Requires the `fire`
scope.

### `POST /v1/fire`

**Request**

| Field | Type | Notes |
|-------|------|-------|
| `type` | string (1–64) | The template/alert type to fire. Required. |
| `context` | object | Variables for rendering the title/message. |
| `test` | bool | Default `false`. Marks the notification as a test: `is_test` in the log, a Test badge, de-duplicated apart from real fires, no action buttons. With the **`admin`** scope (or an admin session) it also skips throttle, the delivery gate, quiet hours and de-duplication; with a `fire` key it is gated and counted like any other fire, and `suppressed_reason` says why one was held. |
| `source` | string | Optional free-text origin tag for the audit/log. |
| `idempotency_key` | string (1–128, `A-Za-z0-9._:@/-`) | Optional. Makes the fire part of an **episode** — see below. Scoped to the calling key. Ignored when `test` is true. |
| `status` | `firing` \| `resolved` | Default `firing`. `resolved` closes the episode named by `idempotency_key` (required then). |
| `resolved_type` | string | Template sent when the episode resolves; taken from the fire that opens it. |

```bash
curl -X POST https://host/v1/fire \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"type":"disk_full","context":{"host":"nas","used_pct":93},"source":"backup-script"}'
```

**Response** (`FireResponse`)

```json
{ "id": "ntf_1794139677372_7fc1…",
  "dispatched": true,
  "channels": ["ui_default", "telegram_main"],
  "status": "sent",
  "suppressed_reason": null,
  "title": "Disk almost full on nas: 93%",
  "message": "Free some space before writes start failing.",
  "severity": "warning" }
```

- `id` — the `notifications_log` row id. Always present (even when
  suppressed) so the caller can correlate.
- `dispatched` — `true` if the status is `sent` or `partial`.
- `channels` — channels that accepted the message on this attempt.
- `status` — see **[Delivery & outbox semantics](#delivery--outbox-semantics)**.
- `suppressed_reason` — why it was gated (e.g. `throttled`, `snoozed`,
  `gated` (quiet hours), `inhibited`, `below_gate` (the template's delivery
  gate), `disabled`, `unknown_type`, `duplicate` — a rule that went false and
  true again inside the idempotency window with the same values, recorded but
  not sent twice), or `null`.

If the `type` has no configured template, the fire is accepted, logged
as `unknown_type`, and nothing is dispatched (a safe no-op you can see
in the log).

#### Episodes (`idempotency_key`)

A script that reports the same problem every minute should notify once, not
every minute, and say when it is over. Send an `idempotency_key`:

```bash
# every check while the disk is full — notifies once
curl -X POST https://host/v1/fire -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"type":"disk_full","context":{"host":"nas"},"idempotency_key":"nas-disk","resolved_type":"disk_ok"}'
# when it is fixed
curl -X POST https://host/v1/fire -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"type":"disk_full","context":{"host":"nas"},"idempotency_key":"nas-disk","status":"resolved"}'
```

| Call | `episode` in the response | Effect |
|------|---------------------------|--------|
| first `firing` | `opened` | Opens an incident (`source_kind=fire`) and notifies. |
| `firing` while open | `repeat` | Nothing is sent; the response describes the episode's notification. Escalation keeps running until someone acknowledges. **Exception:** while no firing notice of the episode has gone out (the first was snoozed, in quiet hours, throttled, or failed on every channel), a repeat goes through the gates again and is sent once nothing mutes it. The announcement happens on a repeat, not by itself: a caller that fires once and never repeats is not announced later. |
| `resolved` | `resolved` | Closes the incident, cancels pending escalation, sends `resolved_type` if the opening fire named one. |
| `resolved`, nothing open | `not_found` | No-op (safe to repeat). |

The response also carries `incident_id`. When no notification describes the
call (`not_found`, a resolution without a notice) `status` is the `episode`
value and `title` / `message` are empty. Acknowledge in Klopot
(`POST /v1/incidents/{id}/ack`, the UI, Telegram); a resolution is not an
acknowledgement. Keys are per caller: two API keys using the same
`idempotency_key` have separate episodes.

### Delivery & outbox semantics

alertd guarantees **at-least-once** delivery. On a fire, the
`notifications_log` row **and** one `deliveries` row per routed channel
are written in a single transaction **before** any external send. A
synchronous first attempt is made; retryable failures stay queued and a
background worker retries them with exponential backoff and resumes
after a restart.

The `status` field reflects the roll-up of the per-channel deliveries:

| `status` | Meaning |
|----------|---------|
| `sent` | Every routed channel delivered. |
| `partial` | Some channels delivered, some permanently failed. |
| `pending` | At least one delivery is still queued/retrying. **Not an error** — the notification is durably recorded and will be delivered. |
| `failed` | Every channel permanently failed (after retries). |
| `suppressed` | Gated before dispatch; see `suppressed_reason`. |
| `cancelled` | An incident recovered before delivery; nothing is still needed. |

**Integration note:** treat `pending` as *success-in-progress*, not a
failure. Do **not** add your own retry loop for transient channel
errors — alertd owns retries. A stable `idempotency_key`
(`<notification_id>:<channel>`) is attached per delivery so destinations
that support dedup can drop duplicates.

---

## Alerts log

### `GET /v1/log`

Paged query over fired notifications. Filters: `type`, `severity`
(`info`/`warning`/`critical`), `suppressed` (bool), `delivery_status`,
`acknowledged` (bool), `is_test` (bool), `rule_id`, `incident_id`,
`from` / `to`, `search`, plus `skip`/`limit`.

```bash
curl -H "X-API-Key: $KEY" \
  "https://host/v1/log?severity=critical&acknowledged=false&limit=20"
```

### `GET /v1/log/{id}`

Requires `read`. Returns the notification plus a `deliveries` array with one
entry per channel and purpose (`notification` or `escalation`). Each entry
contains `id`, `channel`, `purpose`, `state` (`pending`, `sent`, `failed`,
`cancelled`), `attempts`, `max_attempts`, `next_attempt_at`, `lease_until`,
`last_error`, `created_at` and `updated_at`. Timestamps are UTC with a `Z`
suffix. Frozen channel configuration, credentials and idempotency keys are
excluded. Historical or suppressed notifications may have an empty array.
The paginated list response does not include delivery details.

List/detail also include nullable `incident_id` and `incident_event`
(`firing` / `resolved`). Filter the list with `?incident_id=<id>` for one
episode's history. `delivery_status=cancelled` means all initial deliveries
were stopped on recovery. Already-sent channels retain their delivery facts.

`attempts` counts transport attempts; circuit-breaker/rate-limit deferrals
do not spend an attempt. `next_attempt_at` is the scheduled time; an active
`lease_until` can delay another worker's attempt. The admin log drawer shows
these details and has a **Refresh deliveries** button.

### `POST /v1/log/{id}/ack`

Acknowledge a notification (requires `ack`). `GET /v1/log/stats`
(`read`) returns counts over a time window (`?window=` e.g. `30m`, `24h`
(default), `7d`).

Acknowledgement also cancels pending, unleased escalation deliveries. An
in-flight send may complete; the worker checks acknowledgement again before
any escalation retry. Initial notification deliveries continue normally.

For an incident-linked notification, ack acknowledges the whole incident,
including future repeats, without resolving it.

## Incidents

Opt in per rule with `incident_enabled=true`. New rule fields are
`recovery_expr` (optional; default: successful false trigger),
`recovery_persist_n` (default 1) and `resolved_template_type` (optional; null
means silent resolution). Existing rules keep their previous behaviour.

- `GET /v1/incidents`: `read`; filters `state=active|resolved`, `acknowledged`,
  `rule_id`, `search`, `skip`, `limit`. Omit state for all episodes.
- `GET /v1/incidents/{id}`: `read`; detail with opening/recovery values,
  duration, acknowledgement, resolution time/reason. Timestamps are UTC.
- `POST /v1/incidents/{id}/ack`: `ack`; idempotent, preserves first actor/time,
  stops escalation, leaves the incident active.
- `POST /v1/incidents/{id}/resolve`: `ack`; requires
  `{"reason":"Device replaced"}`. Idempotent manual closure, independent
  from acknowledgement; does not announce telemetry recovery. A persistent
  trigger opens a new episode after the required new confirmations.

Example: `condition_expr: "temperature > 80"`, `persist_n: 2`,
`recovery_expr: "temperature < 75"`, `recovery_persist_n: 2` and
`resolved_template_type: "temperature_normal"`. The recovery condition is
only checked while an incident is open. Missing data and evaluation errors
interrupt the confirmations and keep the incident active.

On recovery, alerts and escalations still pending are cancelled; sends
already in flight may complete. The recovery template uses its own routing,
severity, snoozes, quiet hours and throttling. Its context holds the current
values plus `_incident.id`, `_incident.rule_name`, `_incident.event`,
`_incident.opened_at`, and `_incident.duration_sec` on recovery.

Changing the condition or the incident configuration closes the old episode
with reason `rule_reconfigured`, without a recovery message. Disabling or
deleting the rule keeps active incidents for manual review. The UI has an
**Incidents** page, links from the log and settings in the rule editor.
Details: [Incidents and recovery](INCIDENTS.md).

---

## Snooze (mute)

### `POST /v1/snooze`

Mute by scope until a time. Requires `ack`.

```bash
curl -X POST https://host/v1/snooze \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"scope":"type","target":"disk_full","until":"2026-12-01T00:00:00Z"}'
```

- `scope`: `type` (a template type; `"*"` = maintenance mode, mutes
  everything), `rule` (a rule id), or `channel` (a channel name —
  strips just that destination).
- `GET /v1/snooze` (`read`) lists snoozes (filters `scope`, `target`,
  `active`); `DELETE /v1/snooze/{id}` (`ack`) ends one.

---

## Live state & streams

### `GET /v1/state`

A snapshot of the live variable cache (current value, age, source) —
useful for debugging what rules see. Requires `read`.

### WebSocket `GET /v1/stream/notifications`

Live feed of dispatched notifications (the UI channel). Auth with
`?api_key=...` (browsers can't set WS headers) or the session cookie;
requires `read`.

### WebSocket `GET /v1/stream/state`

Live feed of every variable update (debug firehose). Same auth, `read`.

```js
const ws = new WebSocket("wss://host/v1/stream/notifications?api_key=" + key);
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

---

## Configuration (bulk / disaster recovery)

- **`GET /v1/config/export`** — the full config as a portable YAML pack
  (inputs, variables, templates, channels, routes, rules, schedules,
  settings). `?mask_secrets=true` rewrites literal secrets as
  `env:UNKNOWN_*` placeholders for safe sharing. Requires `admin`.
- **`POST /v1/config/validate`** (`admin`) — validate a YAML pack without writing;
  returns a plan `{ ok, creates, updates, errors, warnings }`.
- **`POST /v1/config/import?apply=true`** — apply a pack in one
  transaction (dry-run without `apply=true`). Masked `env:UNKNOWN_*`
  placeholders are never written over a live secret.

```bash
curl -H "X-API-Key: $KEY" https://host/v1/config/export > alertd.yaml
curl -X POST "https://host/v1/config/import?apply=true" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/yaml" \
  --data-binary @alertd.yaml
```

### Selective export and item-by-item import

`GET /v1/config/export` accepts, besides `mask_secrets`:

| Parameter | Effect |
|-----------|--------|
| `sections` | Comma list of `inputs, templates, channels, variables, rules, routes, schedules`. Templates bring their routes. |
| `category` | Templates of that category and rules whose template is in it (case-insensitive, `__none__` = uncategorized). |
| `names` | Comma list of identifiers to keep (template type, rule / variable / input / channel / schedule name). |
| `with_dependencies` | For the selected rules, also their templates (with routes) and the variables they read. |
| `pack_id`, `pack_name`, `pack_description`, `pack_version` | Wrap the export in a `pack:` header (see [Packs](#packs)). |

Without any of them the export is the full configuration, as before.

`POST /v1/config/import/preview` (YAML body) classifies every item of a pack
against the live configuration — nothing is written:

```json
{ "ok": true, "errors": [], "warnings": [],
  "counts": { "new": 1, "identical": 4, "differs": 1 },
  "items": [ { "section": "rules", "key": "disk_full_v1", "status": "differs",
               "changes": [ { "field": "persist_n", "current": 2, "incoming": 5 } ] } ] }
```

Items are compared as import would store them: a field the file omits takes
its import default, so it shows up as a change when that differs. Route keys
are `<template>→<channel>`.

`POST /v1/config/import/apply` (JSON, scope `admin`):

```json
{ "yaml": "<the pack>",
  "decisions": { "templates:disk_full": "copy", "rules:disk_full_v1": "overwrite",
                 "routes:disk_full→old_channel": "skip" },
  "default_existing": "skip" }
```

New items are imported unless their decision is `skip`; identical items are
left alone; an existing item that differs follows its decision, else
`default_existing` (default `skip`). `copy` stores it as `<name>_copy`
(`_copy2`, …) — not for routes; a copied template takes the pack's rules,
routes and schedules that reference it. The response adds `created`,
`overwritten`, `skipped`, `copied` (`{"templates:x": "x_copy"}`) and `applied`
to the usual plan fields. One transaction, audited as `config.import`, then a
hot reload.

## Form metadata

### `GET /v1/meta/kinds`

Returns the field schemas for every input/channel/variable kind (what
the admin UI builds its forms from) plus webhook presets (Slack,
Discord, Teams, …). Read this to know which config fields a given kind
accepts. Each channel kind also carries `intrusive` (true for `sms` and
`pushover`: can wake someone up or costs money per message); the template
editor warns when an `info` template would reach such a channel.

### Activity log

What reached Klopot and what it sent — see **[Activity log](ACTIVITY_LOG.md)**.
`GET /v1/activity/requests` (filters: `method`, `route`, `status` = `4xx`…, `search`,
`actor`, `ip`, `trace_id`, `webhooks=true`, `from` / `to`),
`GET /v1/activity/requests/{id}` (with bodies — admin), `GET /v1/activity/sources?hours=24`,
`GET /v1/activity/attempts` (`channel`, `notification_id`, `kind`, `outcome`),
`GET /v1/activity/events` (`source_kind`, `source_name`, `event`), and the
rules that decide what is kept: `GET /v1/activity/rules` (`read`),
`POST` / `PATCH` / `DELETE /v1/activity/rules` (`admin`),
`POST /v1/activity/rules/preview?hours=` (`read`). All other activity reads
need `read`.

### Web Push devices

Alerts as system notifications on phones and computers — see
**[Web Push](WEB_PUSH.md)**. `GET /v1/push/config` (scope `read`) →
`{enabled, public_key, channel, reason}`. A browser registers itself with
`POST /v1/push/subscriptions` — body = `PushSubscription.toJSON()`
(`endpoint`, `keys.p256dh`, `keys.auth`) — from a **signed-in session** (an
API key is refused: it is not a device); only Apple / Google / Mozilla /
Microsoft endpoints are accepted (422 otherwise). The same endpoint again
refreshes the keys (200) instead of adding a device (201).
`GET /v1/push/subscriptions` (scope `read`) lists devices without their
endpoint (`service` = host and tail, `endpoint_hash` = sha256 so a browser can
find itself); `PATCH` (`label`, `min_severity`, `enabled`), `DELETE` and
`POST /v1/push/subscriptions/{id}/test` need `admin` and are audited.

### Setup guide

`GET /v1/setup/status` (scope `read`) says what a new installation still
needs. Every step is derived from the live configuration, so it is right
however things were set up:

| Step | Done when |
|------|-----------|
| `channel` | an enabled channel other than the built-in `ui` / `banner` exists |
| `channel_tested` | such a channel passed `POST /v1/channels/{id}/test` (audited as `channel.test`) or delivered an alert |
| `source` | an input exists, or an enabled API key with the `fire` scope |
| `rules` | a rule exists, or a template outside the built-in `Self-monitoring` category |
| `first_alert` | the notification log has a row |

The response also has `complete`, `dismissed` and `timezone` (`ALERTD_TZ`).
`POST /v1/setup/dismiss` / `POST /v1/setup/reopen` (scope `admin`) hide or
show the guide; both are audit events (`setup.dismiss` / `setup.reopen`).

### Packs

A pack is an import document with a `pack:` header and parameters
(`${name}`); the format and the catalog are in **[Packs](PACKS.md)**.

| Call | Scope | What it does |
|------|-------|--------------|
| `GET /v1/packs` | read | The built-in catalog: id, name, description, tags, parameters, item counts |
| `GET /v1/packs/{id}` | read | One catalog pack, plus its YAML |
| `POST /v1/packs/inspect` | admin | Header and parameters of your own pack (`{"yaml": …}`) |
| `POST /v1/packs/preview` | admin | `{"pack_id" or "yaml", "params"}` → parameters checked, then the per-item preview of `/v1/config/import/preview` |
| `POST /v1/packs/apply` | admin | Same body + `decisions` / `default_existing` → installs in one transaction, audited as `pack.install` |

```bash
curl -X POST https://host/v1/packs/apply -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"pack_id":"sensor-threshold","params":{"key":"freezer","topic":"home/freezer/t","threshold":-10}}'
```

Parameter problems come back in `errors` as `parameter <name>: <reason>`.
Export any selection as a pack with `GET /v1/config/export?…&with_dependencies=true&pack_id=my-pack`.

## Settings & audit

- **`GET /v1/settings`** (`read`) — the effective runtime settings
  (retention windows, breaker thresholds, timezone…), each tagged with its
  source (`env` / `default`). Read-only: there is no `PATCH`; values come
  from the environment at startup — see [Deploy](DEPLOY.md). Secrets are
  masked or omitted.
- **`GET /v1/audit`** (`read`) — paged history of admin actions (who
  changed what, with before/after and a trace id). Filters: `action`,
  `resource_kind`, `resource_id`, `actor_name`, `trace_id`, `from` / `to`.

---

## Alertmanager / Grafana receiver

An input of `kind=alertmanager` accepts Prometheus Alertmanager
(`webhook_configs`, payload v4) and Grafana alerting (webhook contact point)
at `POST /v1/inputs/{id}/webhook`. The token goes in `X-Input-Token` or
`Authorization: Bearer` (the same endpoint serves `webhook` and
`sms_inbox` inputs). Every inbound input requires its token unless its config
says `auth_required: false`; saving one that requires a token without having
one is refused (`422`). An id that is no live inbound input (missing, another
kind, disabled) and a wrong or missing token all get the same `401` ("Unknown
input or wrong token"), and count against the sending address: after five in
a minute every request from it gets `429` (`Retry-After: 60`) — the input's
editor lists its recent requests with status and address. A token needs at
least 32 characters when it is set or changed; an older, shorter one keeps
working and is flagged (`token_too_short` on `GET /v1/inputs`). An input may
limit its own requests (`rate_limit_per_min` in its config): over it, `429`
with `Retry-After`. Alertmanager:

```yaml
receivers:
- name: klopot
  webhook_configs:
  - url: https://alerts.example.com/v1/inputs/<id>/webhook
    send_resolved: true
    http_config:
      authorization: { credentials: <token> }
```

Every alert of the group is an episode keyed by input + `fingerprint`
(`incidents.source_kind=alertmanager`): `firing` opens it and notifies once,
Alertmanager's re-sends notify nothing, `resolved` closes it (and sends
`resolved_type`). A firing with a newer `startsAt` closes the previous
episode as `superseded`; a resolution for an older `startsAt` is ignored.

Template choice per alert: a template named like `labels.<type_label>`
(default `alertname`) if `label_types` allows it (exact names or patterns,
e.g. `["am_*"]`; empty = the label chooses none, so a token holder cannot
pick any template) → else `type_by_severity[labels.severity]` (or its
`default`) → else `default_type` (default `alertmanager_alert`). Unknown
names are never dropped. Templates read `{labels.instance}`,
`{annotations.summary}`, `{status}`, `{alert.generator_url}` …

At most `max_alerts` (default 200, at most 1000) are processed per request.
Each new fingerprint opens an episode and sends a notice, so an input also
has budgets for what it opens: `max_new_episodes_per_min` (default 60,
counted like a rate limit — a quiet input may open that many at once) and
`max_active_episodes` (default 500 open at once). A firing alert past either
is not opened (`over_budget`); Alertmanager sends it again while it fires,
and it opens once there is room. Repeats and resolutions are never budgeted.
The truncated alerts, Alertmanager's own `truncatedAlerts` and the ones over
budget fire one `alertmanager_truncated` notice per request (context
`input`, `truncated`, `over_budget`). Bodies over
`ALERTD_MAX_ALERTMANAGER_BYTES` (1 MiB) get 413, non-JSON or a body without
`alerts` 400. Response:

```json
{ "status": "accepted", "input": "prom", "alerts": 3, "opened": 1, "repeat": 1,
  "resolved": 1, "ignored": 0, "over_budget": 0, "truncated": 0, "errors": [] }
```

## Rules and variables: status, usage, bulk actions

### Rule evaluation status

Every rule carries `eval_status`, derived from `consecutive_eval_errors` and
`last_eval_error`:

| `eval_status` | Meaning | Counted towards auto-disable |
|---------------|---------|------------------------------|
| `ok` | Last evaluation succeeded | — |
| `no_data` | Waiting for an input: a dotted variable it reads has no value (`last_eval_error` starts with `missing input:`) | No |
| `error` | The expression fails (`NameError`, type error, …) | Yes |

A successful evaluation clears `last_eval_error`, including a `no_data`
message. A disabled rule keeps its last message as history.

`GET /v1/rules` filters: `eval_status`, `has_error` (`true` = `error`),
`enabled`, `template_type`, `category` (of the rule's template,
case-insensitive; `__none__` = uncategorized), `never_fired`, `search`.

### `POST /v1/rules/bulk/enabled` (scope `admin`)

```json
{ "ids": [12, 14, 99], "enabled": false }
→ { "updated": [12, 14], "unchanged": [], "not_found": [99] }
```

One transaction, one `rule.update` audit entry per changed rule, one engine
reload (only if something changed). Use it instead of a `PATCH` per rule.

### Variable live state and usage

`GET /v1/variables` and `GET /v1/variables/{name}` add, per variable:

| Field | Meaning |
|-------|---------|
| `last_value`, `last_value_at`, `age_sec`, `is_stale` | From the in-memory state cache |
| `value_state` | `fresh`, `stale` (older than its window), `missing` (no value since start-up) |
| `used_by_rules` | Rules that read it: `vars_extract`, `condition_expr`, `recovery_expr`, including names passed as strings to helpers such as `var_age("x")` |
| `used_by_variables` | Computed variables whose `formula` reads it |

List filters: `source`, `enabled`, `input_id`, `state`
(`fresh`/`stale`/`missing`), `stale` (bool, kept for compatibility), `used`
(`true`/`false`), `search`.

### Template icon and category

`icon` must be an emoji: at least one pictographic symbol and no letters,
digits or `?` (mis-encoded values such as `âš¡` and a lost `??` are rejected
with 422, on create, update and config import). Empty clears it. A `category`
that differs from an existing one only by case is stored with the existing
spelling.

## Configuration resources (CRUD)

Each of these is a standard REST collection: `GET` (list, paginated),
`POST` (create), `GET /{id|name}` (one), `PATCH /{id|name}` (update),
`DELETE /{id|name}`. All writes require `admin` and are audited. Reads need
`read`. Field schemas come from `GET /v1/meta/kinds`.

| Collection | What it is |
|------------|------------|
| `/v1/inputs` | Declared sources: MQTT / HTTP-poll / webhook / sms_inbox / **alertmanager** (see below). Plus `GET /{id}/health` and `POST /{id}/restart`. |
| `/v1/variables` | Named values extracted from inputs (`mqtt`, `aggregate`, `constant`, `computed`, `schedule`). |
| `/v1/templates` | Per-type title/message/severity/icon, cooldown (`min_repeat_min`), quiet hours, optional delivery gate (`gate_variable` + `gate_min`; `require_pv_kw` is its deprecated alias), `category`. Plus `POST /{type}/preview` (`read`, render without sending) and the routes — see [Template → channel routing](#template--channel-routing). |
| `/v1/channels` | Delivery destinations (ui/banner/telegram/sms/email/push/webhook/mqtt/**ntfy**/**gotify**/**pushover**) + rate limit + quiet hours. Plus `POST /{id}/test` (sends a test message, audited `channel.test`), `GET /{id}/health`, `GET /{id}/usage` (templates routed to it) and `POST /{id}/breaker/reset` (forces a tripped breaker closed). |
| ntfy | `kind=ntfy`: `server_url` (default `https://ntfy.sh`), `topic` (write-only: on ntfy the topic name is the credential; or `topic_ref`), `token` (write-only, Bearer), `priority_map` (default info 2 / warning 3 / critical 5), `tags`, `admin_url` (click link + View button to the log entry). Publishes with ntfy's JSON API (UTF-8 titles); the ntfy message id is stored as the delivery's `provider_ref`. No dedup at ntfy: at-least-once. |
| Gotify | `kind=gotify`: `server_url`, `app_token` (write-only, sent as `X-Gotify-Key`), `priority_map` (default info 2 / warning 5 / critical 8), `admin_url` (tap opens the alert). Message id → `provider_ref`. |
| Pushover | `kind=pushover`: `user_key`, `app_token` (both write-only), `device`, `priority_map` (default info -1 / warning 0 / critical 1), `admin_url`. **Emergency** (priority 2, repeat until acknowledged) only for the severities in `emergency_for` (default none), with `retry_sec` (≥ 30) and `expire_sec` (≤ 10800). The emergency receipt is the delivery's `provider_ref`; acknowledging in Klopot cancels it, acknowledging in the Pushover app acknowledges the alert in Klopot (polled every ~60 s, actor `pushover:<device>`). Intrusive kind. |
| MQTT output | `kind=mqtt`, topic_template, qos, retain, host/port, credential refs, tls, payload_template, availability and heartbeat. [Reference](MQTT_OUTPUT.md). |
| Telegram actions | Channel config: `inline_actions` (default false), numeric `chat_id`, `allowed_user_ids` (JSON list), optional explicit `any_chat_member`, `actions_locale=en\|ro`, `admin_url`. Polling starts automatically when enabled; no public callback endpoint. [Setup](TELEGRAM.md). |
| `/v1/rules` | Condition expression + `persist_n` + eval interval + `inhibited_by` + operator-visible trigger summary. Plus `GET /by-name/{name}`, `POST /validate` (`read`, check an expression), `POST /{id}/eval-now` (`read`, evaluate without firing), `POST /{id}/test` (`admin`, test fire) and [`POST /bulk/enabled`](#post-v1rulesbulkenabled-scope-admin). |
| `/v1/schedules` | Cron-driven fires of a template type. Plus `GET /preview?cron=…&n=…` (next firings) and `POST /{id}/test` (fire once now). |
| `/v1/api_keys` | Caller authentication — see [API keys](#api-keys). |

**Create examples**

```bash
# A channel (UI WebSocket — no secrets)
curl -X POST https://host/v1/channels -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"ui_default","kind":"ui","config":{}}'

# A template
curl -X POST https://host/v1/templates -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"disk_full","severity":"warning",
       "title_template":"Disk almost full on {host}: {used_pct}%",
       "message_template":"Free some space before writes start failing.","min_repeat_min":30}'

# Route the template to the channel
curl -X PUT https://host/v1/templates/disk_full/channels -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '[{"channel_name":"ui_default","severity_min":"info"}]'

# A rule that fires it from a live variable
curl -X POST https://host/v1/rules -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"disk_full_rule","template_type":"disk_full",
       "condition_expr":"used_pct > 90","persist_n":3,"eval_interval_sec":10}'
```

### Template → channel routing

A template reaches the channels it is routed to (`template_channels`, with
per-route `severity_min`, `enabled` and `channel_overrides`):

- `GET /v1/templates/{type}/channels` (`read`) lists the routes.
- `PUT /v1/templates/{type}/channels` (`admin`) replaces the whole set
  atomically; each item names its channel by `channel_id` or
  `channel_name`. Audited as `route.set`.
- `DELETE /v1/templates/{type}/channels/{channel_id}` (`admin`) removes one.

Routes also travel with config import/export.

## API keys

All `/v1/api_keys` calls need `admin`.

| Call | What it does |
|------|--------------|
| `GET /v1/api_keys` | List (filter `enabled`); never shows the secret, only its prefix |
| `POST /v1/api_keys` | `{"name", "scopes", "expires_at"?, "enabled"?, "allowed_cidrs"?, "rate_limit_per_min"?}` → 201 with the plaintext `key`, shown **once** |
| `GET` / `PATCH` / `DELETE /v1/api_keys/{id}` | Read, change (scopes, expiry, enabled, allowed addresses, rate limit — `null` removes it), delete |
| `POST /v1/api_keys/{id}/rotate?grace_sec=N` | New plaintext key with the same scopes, expiry, allowed addresses and rate limit; the old one is revoked now, or after `N` seconds (0–600, default 0) |

`allowed_cidrs`: IPs or CIDRs (IPv4/IPv6, at most 64) the key may be used
from; empty = any address. From anywhere else the key gets `403` and counts
as a wrong key for that address ([AUTH_MODEL](AUTH_MODEL.md#source-allowlist)).
`GET /v1/auth/me` returns `client_ip`, the address Klopot sees you at.

`rate_limit_per_min`: requests a minute the key may make (1–60000); `null` =
no limit. A quiet key may send that many at once, then one every 60/N
seconds; over it the request gets `429` with `Retry-After`, the seconds until
the next one fits ([AUTH_MODEL](AUTH_MODEL.md#rate-limit)). Wait that long
before retrying.

## Browser session endpoints

Used by the admin UI; all except login need the session cookie (and
`X-CSRF-Token` on unsafe methods): `POST /v1/auth/login`,
`POST /v1/auth/logout`, `GET /v1/auth/me`, `POST /v1/auth/password`,
`GET /v1/auth/sessions`, `DELETE /v1/auth/sessions` (all other sessions),
`DELETE /v1/auth/sessions/{id}`. Details: [Auth model](AUTH_MODEL.md).

## Client examples

Any HTTP client works. A ~30-line async shim makes the service callable
from Python:

```python
import httpx

class AlertdClient:
    def __init__(self, base_url: str, api_key: str):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=5.0,
        )

    async def fire(self, type: str, **context) -> dict:
        r = await self._client.post("/v1/fire", json={
            "type": type, "context": context,
        })
        r.raise_for_status()
        return r.json()

# Usage
alertd = AlertdClient("https://host", "alertd_xxxxxxxxxxxxxxxx")
await alertd.fire("backup_failed", job="daily_db", error="timeout")
```

See **[Getting Started](GETTING_STARTED.md)** for the full end-to-end
walkthrough, and **[the expression language](EXPRESSION_LANGUAGE.md)**
for rule condition syntax.
