# Architecture

## Overview

Klopot (`alertd`) is an asynchronous Python microservice that turns
**declarative configuration** (inputs, rules, templates, channels,
schedules, stored in MySQL) into **dispatched notifications** (via UI
WebSocket, Telegram, SMS, email, push, webhook, plus future kinds).

The service is stateless from the request perspective; all persistent
state (rules, log, throttle counters) lives in MySQL. A single
background `AlertEngine` task subscribes to declared inputs, keeps a
live state cache, ticks every N seconds, and feeds matched rules to
the dispatcher.

## Founding principles

1. **API-everything.** Every configuration item is mutable via REST.
   Inputs, variables, templates, rules, channels, schedules, API
   keys, snoozes, settings — all CRUD via `/v1/...`. The UI is just
   another API consumer. No "DB-only" knobs. See
   [`API.md`](API.md) for the full surface (and the live OpenAPI at
   `/openapi.json`).

2. **Pluggable everything.** Inputs and channels are plug-ins
   declared in a registry. Adding a new kind (e.g., `discord_webhook`,
   `file_tail`, `voice_call`) is a 100-line PR with a defined
   checklist; no architectural changes. See
   [`EXTENSIBILITY.md`](EXTENSIBILITY.md).

3. **Source-agnostic + sink-agnostic.** Nothing in the service
   assumes a particular domain. The schema, API, and engine work for any
   domain — networking alerts, SaaS uptime, inventory thresholds,
   anything that has values changing over time.

4. **External callers stay dumb.** A caller (Node-RED, a script, a
   future React UI, a third-party app) needs only an API key and an
   alert type. It does NOT need to know about channels, throttling,
   credentials, or templates. `POST /v1/fire {type, context}` and
   the service does the rest.

5. **Hot reload.** Edit a rule in the UI → the running engine sees
   the new condition on the next tick. No restart, no deploy, no
   manual refresh.

6. **Audit trail.** Every admin write goes through middleware that
   records `{actor, action, before, after, ts}` in `audit_log`.
   Useful for "who disabled the SOC critical alert?"

7. **Versioned + backwards-compatible.** All routes under `/v1/`.
   Old API versions stay live for 1 year minimum after a `/v2/` is
   issued.

## Block diagram

```
┌────────────────── EXTERNAL CALLERS ─────────────────┐
│  Web app      Node-RED   scripts    3rd-party app   │
└──────────┬──────────┬──────────┬──────────┬─────────┘
           │ HTTP/WS  │ HTTP     │ HTTP/WS  │ HTTP
           └──────────┴──────────┴──────────┘
                          │
                          ▼
┌──────────────────── Klopot / alertd (FastAPI) ───────────────┐
│  port 5090                                                    │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  REST + WebSocket API (versioned /v1/)                   │ │
│  │  ├─ POST  /v1/fire                                       │ │
│  │  ├─ GET   /v1/log                                        │ │
│  │  ├─ CRUD  /v1/templates  /v1/rules  /v1/channels         │ │
│  │  │   /v1/inputs                                          │ │
│  │  ├─ POST  /v1/snooze                                     │ │
│  │  ├─ POST  /v1/log/{id}/ack                               │ │
│  │  ├─ WS    /v1/stream                                     │ │
│  │  └─ GET   /v1/health  /v1/metrics  /docs                 │ │
│  └────────────┬────────────────────────────────────────────┘ │
│               │                                               │
│  ┌────────────▼────────────────────────────────────────────┐ │
│  │  AlertEngine (background asyncio task, single instance) │ │
│  │                                                          │ │
│  │   Inputs (plug-in adapters)                             │ │
│  │   ┌─────────┐  ┌──────────┐  ┌─────────┐               │ │
│  │   │ MQTTSub │  │HTTPPolls │  │WebhookRx│               │ │
│  │   └────┬────┘  └────┬─────┘  └────┬────┘               │ │
│  │        └─────────────┼─────────────┘                    │ │
│  │                      ▼                                  │ │
│  │   StateCache (in-memory dict, optional Redis)           │ │
│  │      { var_name: { value, ts, source } }                │ │
│  │                      │                                  │ │
│  │                      ▼                                  │ │
│  │   RuleEvaluator (10s tick + on-event for criticals)     │ │
│  │   - Loads enabled rules from DB                         │ │
│  │   - Evaluates condition_expr (simpleeval)               │ │
│  │   - Updates rule_state.consecutive_match_count          │ │
│  │   - When persist_n satisfied: builds FireEnvelope       │ │
│  └────────────┬────────────────────────────────────────────┘ │
│               │                                               │
│  ┌────────────▼────────────────────────────────────────────┐ │
│  │  Dispatcher                                              │ │
│  │   1. idempotency check (5min, hash of vars)             │ │
│  │   2. gating pipeline:                                   │ │
│  │      - template.enabled?                                │ │
│  │      - active snooze on type/rule/channel?              │ │
│  │      - throttled? (last_fire < min_repeat_min)          │ │
│  │      - quiet hours? (strip channels in window)          │ │
│  │   3. render title + message (Pydantic-validated)        │ │
│  │   4. persist row to notifications_log                   │ │
│  │   5. submit one async DispatchTask per allowed channel  │ │
│  │   6. return DispatchResult immediately (async dispatch) │ │
│  └────────────┬────────────────────────────────────────────┘ │
│               │                                               │
│  ┌────────────▼────────────────────────────────────────────┐ │
│  │  Channel adapters (plug-ins, with circuit breakers)     │ │
│  │   ┌────┐ ┌────────┐ ┌─────┐ ┌──────┐ ┌────┐ ┌────────┐ │ │
│  │   │ ui │ │telegram│ │ sms │ │email │ │push│ │webhook │ │ │
│  │   │ WS │ │  HTTP  │ │HTTP │ │SMTP  │ │VAPID│ │  POST  │ │ │
│  │   └────┘ └────────┘ └─────┘ └──────┘ └────┘ └────────┘ │ │
│  │                      │                                  │ │
│  └──────────────────────┼──────────────────────────────────┘ │
│                         ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  MySQL (SQLAlchemy async)                                 │ │
│  │   templates, rules, channels, inputs, variables,         │ │
│  │   notifications_log, throttle_state, rule_state,         │ │
│  │   snooze, api_keys, user_prefs, template_channels        │ │
│  └──────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
                          │
                          ▼
                ┌────────────────────┐
                │  MySQL 8           │
                │  (Docker volume)   │
                └────────────────────┘
```

## Bidirectional integrations

Some integrations are both inputs AND outputs:

### SMS via `sms-gateway`

```
                    ┌────────────────────┐
                    │   sms-gateway      │
                    │ (separate service, │
                    │  HTTP API)         │
                    │  ↕ LTE/GSM modem   │
                    └─┬────────────────┬─┘
                      │                │
              outgoing│                │incoming
              SMS sent│                │SMS received
                      ▼                ▼
              ┌──────────────┐  ┌────────────────────┐
              │ alertd       │  │ alertd             │
              │ /v1/channels │  │ /v1/inputs/        │
              │ kind: sms    │  │ {sms_inbox}/webhook│
              └──────────────┘  └────────────────────┘
```

- **Outgoing**: `kind: sms` channel POSTs to sms-gateway's
  `/api/sms/send` to deliver.
- **Incoming**: `kind: sms_inbox` input — sms-gateway POSTs every
  received SMS to alertd's `/v1/inputs/{id}/webhook`. Each SMS
  becomes a value in the state cache, addressable by phone +
  keyword. Rules can fire on incoming SMS (e.g., `incoming_sms.body
  CONTAINS "STATUS"` fires `status_request`).

The gateway must be able to forward each incoming SMS to a URL. The
`sms_inbox` input understands the Teltonika RUT forwarder's JSON shape
out of the box.

### Email via SMTP + IMAP

- **Outgoing**: `kind: email` channel uses `aiosmtplib` to send.
- **Incoming (future)**: `kind: email_imap` input polls a mailbox,
  parses subject/body, fires events. Useful for forwarded alerts
  from upstream systems.

### HTTP webhooks

- **Outgoing**: `kind: webhook` channel POSTs to any URL. Supports
  Slack, Discord, Mattermost, MS Teams, Home Assistant, custom
  endpoints. Body is a Jinja2-rendered template per channel.
- **Incoming**: `kind: webhook` input registers an endpoint
  `/v1/inputs/{id}/webhook`. External systems POST events; alertd
  treats them like any other input value.

## How external callers fire alerts

The simplest possible integration:

```bash
# any caller — Node-RED, shell, Python, anything
curl -X POST http://localhost:5090/v1/fire \
  -H "X-API-Key: $ALERTD_KEY" \
  -d '{"type": "consumption_high",
        "context": {"current_load_kw": 5.4, "expected_kw": 1.6}}'
```

The caller does NOT need to know:

- Whether the alert routes to Telegram, SMS, push, all of those, or
  none
- Whether it's currently throttled
- Whether the operator is snoozing this type
- How to render the message
- Any channel credentials

That's the whole point: **alertd owns routing**. The caller owns
"this thing happened". They are decoupled.

When the user wants to add a new alert type:

1. Define a **template** in alertd (one API call, or via UI form)
2. Define **rules** that fire it (or none — call `/v1/fire`
   directly from outside)
3. Route the template to channels (one API call per route)
4. Done. The caller just keeps calling `/v1/fire` with the new
   `type`.

When the user wants to silence an alert:

- For a few hours: snooze (`POST /v1/snooze`)
- Permanently: disable the template (`PATCH /v1/templates/{type}
  {enabled: false}`)
- For one channel only: remove the route (`DELETE
  /v1/templates/{type}/channels/{channel_id}`)

## Component responsibilities

### `app/api/` — REST + WebSocket

Pure I/O adapters. No business logic. Each endpoint:

1. Authenticates via `X-API-Key` header
2. Validates body via Pydantic model
3. Calls a `core/` function
4. Maps the result to a Pydantic response model
5. Returns

OpenAPI is auto-generated from FastAPI dependency / response_model
declarations. `GET /docs` and `GET /redoc` are served by FastAPI.

### `app/core/engine.py` — AlertEngine

A single asyncio task started at app boot, kept alive by uvicorn's
event loop. Responsibilities:

- Subscribe to all `enabled=True` rows in `inputs`
- Maintain `state_cache` keyed by variable name
- Tick every N seconds (configurable per rule)
- For each `enabled=True` rule:
  - Build a context dict from `state_cache` filtered by `vars_extract`
  - Evaluate `condition_expr` via `app/core/eval.py`
  - Update `rule_state.consecutive_match_count`
  - If satisfied (≥ `persist_n`), call `dispatcher.fire()`
  - Reset counter on negative match (or after >5min gap, configurable)

The engine NEVER blocks the API. All DB calls go through the
SQLAlchemy async pool with bounded concurrency.

### `app/core/dispatcher.py` — Dispatcher

Public entrypoint: `async def fire(envelope, session)`. It runs the gating
pipeline, renders the template, persists the fire and hands it to the
delivery path below.

### Delivery path — outbox, worker, channel manager

Delivery is **at-least-once**: a crash can duplicate a notification, never
lose one. The pieces, in the order a fire passes through them:

| Step | File | What happens |
|------|------|--------------|
| 1. Persist | `app/core/dispatcher.py` | One transaction commits the `notifications_log` row, one `deliveries` row per routed channel (with the destination config and adapter kind **frozen** at that moment), the dedup claim (`dedup_claims.py`) and the per-type throttle reservation (`gating.py`). Nothing is sent before this commit. |
| 2. First attempt | `app/core/dispatcher.py` | Sends to all channels in parallel, inline, bounded by `FIRST_ATTEMPT_BUDGET_SEC` (45 s). Each row is leased for `FIRST_ATTEMPT_LEASE_SEC` (60 s) so the worker cannot pick it up while the attempt is in flight. Channels that finish inside the budget keep their result; unfinished ones stay `pending`. |
| 3. Send | `app/channels/manager.py` | Per channel: circuit breaker (`circuit_breaker.py`) and rate limiter (`rate_limiter.py`) decide whether to attempt at all, then the adapter's `send()` runs under a hard `adapter_send_timeout_sec` ceiling (30 s). Outbound HTTP goes through `app/utils/safe_http.py`. |
| 4. Record | `app/core/outbox.py` | `apply_attempt` marks the delivery `sent`, or schedules a retry with exponential backoff (30 s, 60 s, 120 s, … capped at 1 h), or marks it `failed` after `MAX_ATTEMPTS` (5) or on a permanent error (channel missing/disabled). A channel that was *not attempted* (breaker open, rate-limited) is **deferred** via `apply_deferral`: retried in 30 s without consuming an attempt, and given up only when the delivery is older than `MAX_DELIVERY_AGE_SEC` (1 h). |
| 5. Retry | `app/core/delivery_worker.py` | A background loop claims due `pending` rows (lease-based compare-and-set, one commit per delivery) and repeats steps 3–4 with the frozen config. This is also what recovers a fire whose first attempt was cut short by a crash or restart. |
| 6. Roll up | `app/core/outbox.py` | `apply_rollup_to_log` folds the per-channel states into the log row's `delivery_status`, `dispatched_to` and `failed_channels`. When every channel has failed terminally, the dedup claim and throttle reservation are released so the next identical fire is not swallowed. The first successful channel counts the fire exactly once (`gating.account_first_success`). |

Things that follow from this design:

- `failed` deliveries are the dead-letter record; they are visible on the
  log row and are not retried again.
- Retention (`app/core/retention.py`) never deletes a notification that
  still has a `pending` delivery.
- The timeouts are ordered on purpose: send ceiling (30 s) < first-attempt
  budget (45 s) < lease (60 s). Changing one without the others can wedge a
  half-open breaker probe or let the worker re-send an in-flight delivery.
- All of it assumes **one process** (see `docs/DEPLOY.md`): the breaker,
  rate limiter and rule engine are in-memory per process.

### `app/core/gating.py` — Gating pipeline

Pure functions. Each gate takes `(template, envelope, db_session)` and
returns either `Allow(channels)` or `Deny(reason)`. Order: enabled,
snoozed, throttled, persist (delegated to engine), quiet_hours
(filters channels). First deny wins.

Persist counter logic moves to the engine — gating only checks
`throttle_state.persist_count` for legacy compatibility, but the
canonical counter is `rule_state.consecutive_match_count` (one row per
rule, vs throttle which is one row per type).

### `app/core/eval.py` — Safe expression eval

Wraps `simpleeval`:

- Allowed names: only those declared in rule's `vars_extract`
- Allowed builtins: `min`, `max`, `abs`, `round`, `bool`, `int`, `float`
- No `__import__`, no `__class__`, no `getattr`/`setattr`/`hasattr`
- No comprehensions (RMS-style, prevents pathological eval)
- 100ms timeout per expression (signal-based on Linux)

### `app/core/rendering.py` — Template rendering

Substitutes `{var}` placeholders with `envelope.context[var]`. Missing
variables render as `[?var]` (visible to operator), not crash.

Optional: also support `%var%` syntax (RMS compatibility) — same
result, two readable styles.

### `app/inputs/` — Input adapters (plug-ins)

Each adapter inherits `BaseInput`. Required:

- `async def start(self, on_value: Callable)` — begin streaming values
- `async def stop(self)` — clean shutdown
- `def health(self) -> dict` — `{connected: bool, last_msg_ts: ...}`

Implementations:

- `MQTTSubscriber` (`mqtt.py`) — wraps `asyncio-mqtt`, reads topic + JSONPath
- `HTTPPollInput` (`http_poll.py`) — asyncio-driven polling at configured interval
- `WebhookInput` (`webhook.py`) — receives POST at `/v1/inputs/{id}/webhook` and
  fires `on_value` (registers a route at engine init)
- `SMSInboxInput` (`sms_inbox.py`) — polls the `sms-gateway` inbox

Supporting core services (started by the lifespan alongside the
engine):

- `app/core/manager.py` — input manager: starts/stops adapters from
  DB config, reports per-adapter health (critical vs optional).
- `app/core/variable_resolver.py` — maps inbound topic/payload →
  typed variables in the state cache (JSON-path extraction,
  aggregates, `_MISSING` skip vs `None` tombstone semantics,
  `stale_after_sec` propagation).
- `app/core/schedule_service.py` — cron schedules (`/v1/schedules`):
  fires templates on `next_fire_at`, survives restarts without
  firing-on-resume.
- `app/core/retention.py` — periodic sweep enforcing
  `log_retention_days` / `audit_retention_days`.

### `app/channels/` — Channel adapters (plug-ins)

Each adapter inherits `BaseChannel`. Required:

- `async def send(self, notif: Notification, config: dict) -> bool`
- `def healthcheck(self) -> dict` — channel reachable?

The channel manager and delivery worker handle retries, circuit breaker
state and `notifications_log` updates (see "Delivery path" above).
Channels are **simple**: send or fail.

Kinds: `ui` (WebSocket), `banner` (persistent UI banner), `telegram`,
`sms`, `email`, `push`, `webhook`. Two per-channel guards wrap every
send:

- `circuit_breaker.py` — opens after N consecutive failures
  (`circuit_breaker_threshold`), half-opens after
  `circuit_breaker_open_sec`; breaker state is published on MQTT.
- `rate_limiter.py` — token bucket per channel
  (`channels.rate_limit_per_min`) so a rule storm can't flood a
  destination.

### `app/db/` — Persistence

SQLAlchemy 2.0 ORM, async session per request. Migrations via Alembic.
Connection pool bounded; transactions via `async with session.begin()`.

## Schema

See [`docs/SCHEMA.md`](SCHEMA.md) for the full DDL. Quick map:

| Table | Owner | Purpose |
|-------|-------|---------|
| `inputs` | admin | declared MQTT/HTTP/webhook sources |
| `variables` | admin | named context variables sourced from inputs |
| `templates` | admin | per-type title/message/severity/icon |
| `rules` | admin | condition_expr + persist_n + vars_extract + **trigger_summary** |
| `channels` | admin | per-channel config (telegram/sms/email/...) |
| `template_channels` | admin | many-to-many template ↔ channel routing |
| `notifications_log` | engine | canonical store of every fire (dispatched + suppressed) |
| `throttle_state` | engine | last_fired_at per type |
| `rule_state` | engine | consecutive_match_count per rule |
| `snooze` | user | scope=type/rule/channel, until |
| `api_keys` | admin | name + hashed key + scopes |
| `user_prefs` | user | per-user channel preferences (future) |

## Failure modes

| Failure | Mitigation |
|---------|------------|
| MQTT broker disconnect | Engine watchdog: if no MQTT message in 5 min, fire built-in `mqtt_disconnected` alert (bypasses normal eval — fired directly by engine) |
| MySQL temporarily unreachable | API returns 503; engine pauses ticks; dispatch tasks already in queue retry up to 60min total |
| Channel adapter panics | Caught in dispatcher; recorded in `failed_channels` JSON; circuit breaker opens; alerts logged but other channels still attempt |
| Expression eval timeout (100ms) | Rule marked `last_eval_error`; rule auto-disabled after 5 consecutive errors (admin notified via built-in alert) |
| Disk full (log table) | Retention task DELETEs entries older than `retention_days` (config, default 90d); table size monitored via Prometheus |
| Service crash | Container restart policy; on boot, engine resumes from DB state (no in-memory state lost — it's all in DB) |

## Deployment

- Image: `ghcr.io/sm26449/klopot`, HTTP on port 5090 (published on
  `127.0.0.1` only)
- Database: MySQL 8 container on a private network (not published)
- TLS: a reverse proxy in front — `compose.traefik.yml` for traefik
- Backups: scheduled `mysqldump` in a sidecar container; 30 days retention
- Healthcheck: `/v1/health/ready`

See [`DEPLOY.md`](DEPLOY.md) for full deployment details.
