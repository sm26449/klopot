# Architecture

## Overview

Klopot (`alertd`) is an asynchronous Python microservice that turns
**declarative configuration** (inputs, rules, templates, channels,
schedules, stored in MySQL) into **dispatched notifications** (via UI
WebSocket, Telegram, SMS, email, Web Push, webhook, MQTT, ntfy, Gotify,
Pushover).

The service is stateless from the request perspective; all persistent
state (rules, log, throttle counters) lives in MySQL. A single
background `AlertEngine` task subscribes to declared inputs, keeps a
live state cache, ticks every N seconds, and feeds matched rules to
the dispatcher.

## Founding principles

1. **API-first configuration.** Inputs, variables, templates, rules,
   channels, schedules, API keys and snoozes — all CRUD via `/v1/...`.
   Runtime settings are environment variables read at start;
   `GET /v1/settings` reports their effective values (there is no settings
   write), and importing the legacy settings row does not change them. The UI is just
   another API consumer. No "DB-only" knobs. See
   [`API.md`](API.md) for the full surface (and the live OpenAPI at
   `/openapi.json`).

2. **Pluggable everything.** Inputs and channels are plug-ins
   declared in a registry. Adding a new kind (e.g., `discord_webhook`,
   `file_tail`, `mbg`) is a 100-line PR with a defined
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
   Useful for "who disabled the disk-full critical alert?"

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
│  │  ├─ WS    /v1/stream/notifications  /v1/stream/state     │ │
│  │  └─ GET   /v1/health  /v1/metrics  /docs                 │ │
│  └────────────┬────────────────────────────────────────────┘ │
│               │                                               │
│  ┌────────────▼────────────────────────────────────────────┐ │
│  │  AlertEngine (background asyncio task, single instance) │ │
│  │                                                          │ │
│  │   Inputs (plug-in adapters)                             │ │
│  │   ┌─────────┐  ┌──────────┐  ┌─────────┐               │ │
│  │   │ MQTTSub │  │HTTPPolls │  │WebhookRx│ (+ sms_inbox, │ │
│  │   └────┬────┘  └────┬─────┘  └────┬────┘  alertmanager)│ │
│  │        └─────────────┼─────────────┘                    │ │
│  │                      ▼                                  │ │
│  │   StateCache (in-memory dict)                           │ │
│  │      { var_name: { value, ts, source } }                │ │
│  │                      │                                  │ │
│  │                      ▼                                  │ │
│  │   RuleEvaluator (per-rule eval_interval_sec, 1 s wake)  │ │
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
│  │      - delivery gate? (gate_variable < gate_min)        │ │
│  │      - quiet hours? (strip channels in window)          │ │
│  │   3. render title + message (Pydantic-validated)        │ │
│  │   4. persist row to notifications_log                   │ │
│  │   5. first attempt inline, all channels in parallel,    │ │
│  │      ≤ 45 s; unfinished ones go to the delivery worker  │ │
│  └────────────┬────────────────────────────────────────────┘ │
│               │                                               │
│  ┌────────────▼────────────────────────────────────────────┐ │
│  │  Channel adapters (plug-ins, with circuit breakers)     │ │
│  │   ┌────┐ ┌────────┐ ┌─────┐ ┌──────┐ ┌────┐ ┌────────┐ │ │
│  │   │ ui │ │telegram│ │ sms │ │email │ │push│ │webhook │ │ │
│  │   │ WS │ │  HTTP  │ │HTTP │ │SMTP  │ │VAPID│ │  POST  │ │ │
│  │   └────┘ └────────┘ └─────┘ └──────┘ └────┘ └────────┘ │ │
│  │   + mqtt, ntfy, gotify, pushover, banner               │ │
│  └──────────────────────┼──────────────────────────────────┘ │
│                         ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  MySQL (SQLAlchemy async)                                 │ │
│  │   templates, rules, channels, inputs, variables,         │ │
│  │   notifications_log, throttle_state, rule_state,         │ │
│  │   snooze, api_keys, template_channels, deliveries, …     │ │
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

### Telegram actions

Telegram channels can opt into a dedicated-bot receiver (migration `0026`). One
long-polling task per credential identity handles all its enabled channels.
Opaque capabilities bind callbacks to a delivery, bot, chat and frozen actor
policy; current permissions are also required. Inbox, offset and accepted local
command commit together. The command applies ack or a fixed-deadline type snooze
in a separate transaction. Provider keyboard cleanup retries independently, and
HTTP acknowledgement / incident resolution also queues cleanup. No public GET
link changes state. See [Telegram setup](TELEGRAM.md).

Some integrations are both inputs AND outputs:

### SMS

```
                    ┌────────────────────┐
                    │ SMS provider       │
                    │ HTTP gateway,      │
                    │ Twilio, or a       │
                    │ Teltonika router   │
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

- **Outgoing**: `kind: sms` channel with a `provider`: `http` (any gateway
  with an HTTP API — URL, method, body template with `{phone}` / `{text}`,
  optional auth), `twilio`, `teltonika` (a RUT router's REST API), or
  `kurier` (the Kurier SMS gateway's own API — severity, a per-recipient
  idempotency key; queued and duplicate count as delivered). A `kurier`
  channel can also turn on Kurier's **watchdog**: `app/core/kurier_watchdog.py`
  pings Kurier every minute with Klopot's health, so Kurier sends an SMS when
  Klopot dies or is stuck, and Klopot alerts when Kurier or its modem stops
  answering ([ADR-0003](adr/0003-kurier-watchdog.md), [OPERATIONS](OPERATIONS.md#kurier-watchdog)).
  Delivery semantics for the `http` provider: `{idempotency_key}` in the body
  template is the same on every retry of a delivery (append `:{phone}` when
  there are several recipients, since each gets its own request); 429 / 503
  wait for `Retry-After`; `success_statuses` (e.g. `[409]` for "duplicate,
  already sent") count as delivered; any other 4xx except 408 fails at once.
- **Incoming**: `kind: sms_inbox` input — the gateway POSTs every
  received SMS to alertd's `/v1/inputs/{id}/webhook`. Each SMS
  becomes a value in the state cache, addressable by phone +
  keyword. Rules can fire on incoming SMS (e.g., `incoming_sms.body
  CONTAINS "STATUS"` fires `status_request`).

The gateway must be able to forward each incoming SMS to a URL. The
`sms_inbox` input understands the Teltonika RUT forwarder's JSON shape
out of the box; any other shape is read as a plain webhook body.

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
  -d '{"type": "disk_full",
        "context": {"host": "nas", "used_pct": 93}}'
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

Every entry point — `POST /v1/fire`, the Alertmanager / Grafana receiver —
goes through the **shared fire service** (`app/core/fire_service.py`), so
routing, gating, dedup and the outbox behave identically for every source.
A caller that sends an `idempotency_key` (and Alertmanager, by fingerprint)
gets an **external episode**: an incident opened on the first firing,
repeats that notify nothing, and a resolution that closes it — see
[INCIDENTS.md](INCIDENTS.md#external-episodes).

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
declarations. `GET /docs`, `GET /redoc` and `GET /openapi.json` are registered by `app/api/docs.py` (public on dev, login- or key-gated on a TLS deploy; the schema is annotated with `x-required-scope`).

### `app/core/engine.py` — AlertEngine

A single asyncio task started at app boot, kept alive by uvicorn's
event loop. Responsibilities:

- Subscribe to all `enabled=True` rows in `inputs`
- Maintain `state_cache` keyed by variable name
- Tick every N seconds (configurable per rule)
- For each `enabled=True` rule:
  - Build a context dict from `state_cache`: `vars_extract` plus the variables
    the expressions read (`engine.rule_context`, shared with eval-now and validate)
  - Evaluate `condition_expr` via `app/core/eval.py`
  - Update `rule_state.consecutive_match_count`
  - If satisfied (≥ `persist_n`), call `dispatcher.fire()`
  - Reset counter on a negative match or an evaluation error

Evaluation outcomes are written to the rule row: a real failure increments
`consecutive_eval_errors` (auto-disable at
`ALERTD_EVAL_ERROR_DISABLE_THRESHOLD`); a *missing input* (a dotted variable
with no value) only records `last_eval_error` and breaks the persist streak.
Any successful evaluation clears the message, and an unchanged message is
not rewritten every tick. The API exposes the result as `eval_status`
(`ok` / `no_data` / `error`).

**Run state** (rules review RL-32, migration 0045): after each evaluation the
engine notes where the rule is — `inactive`, `pending` (true, `persist_n` not
reached), `firing` (fired and still true; an incident rule: its incident is
open), `no_data`, `error` — and writes `rules.run_state` / `run_state_since` /
`last_true_at` plus one `rule_transitions` row **only when it changes**. The
history is capped at 60 rows an hour per rule (the current state is always
written); a failed write is retried at the next evaluation; a condition edit
clears `run_state` in its own transaction (`rule_state_ops`), so a restart
before the first tick does not carry the old condition's `firing`.

**Parametric rules** (ADR-0005, migration 0046): a rule with `for_each`
(`{"n": ["f1", "f2"]}`) is one runtime per value. `app/core/parametric.py`
`RuleView` is the rule as one instance sees it (`{n}` replaced in the
condition, recovery, `vars_extract` and template types; everything else reads
and writes the rule). Runtimes are keyed by the rule id for an ordinary rule and
by `(id, instance)` for an instance; inhibition markers by name or
`(name, instance)` — so every caller and test that uses `engine._rules[rule.id]`
still works. An instance's counters, run state and message live in
`rule_instances`; the rule row holds their summary (the most urgent state,
`… — instance f4` as message, a real error first, the highest error count). The dispatch context gets the
parameter (`n`), which also keeps instances apart in de-duplication. Errors and
auto-disable stay per rule; a missing input stays per instance.

**History** (ADR-0004): `app/core/history.py` keeps, in memory, the variables
and windows the enabled rules (each instance) and computed formulas ask for —
the engine and the input manager pass their needs at every reload
(`set_needs("rules" | "computed", …)`); it subscribes to the state cache's
writes. Until a window is covered the history functions raise
`MissingHistory`, a missing input (`no_data`).

Which rules and computed variables read a variable is derived on demand by
`app/services/references.py` (expressions, `vars_extract`, and names passed as
strings to helpers such as `var_age("x")`), for the admin UI and the `used`
filter on `GET /v1/variables`.

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
| 4. Record | `app/core/outbox.py` | `apply_attempt` marks the delivery `sent`, or schedules a retry with exponential backoff (30 s, 60 s, 120 s, … capped at 1 h), or marks it `failed` after `MAX_ATTEMPTS` (5) or on a permanent error (channel missing/disabled). A channel that was *not attempted* (breaker open, rate-limited) is **deferred** via `apply_deferral`: retried in 30 s without consuming an attempt, and given up only when the delivery is older than `MAX_DELIVERY_AGE_SEC` (1 h). An adapter can also report **backpressure** (`SendResult.retry_after`, from a 429 / 503 `Retry-After`): deferred by exactly that long, breaker untouched — and a **permanent** refusal (`SendResult.permanent`, a 4xx such as 422): failed at once, breaker untouched. |
| 5. Retry | `app/core/delivery_worker.py` | A background loop claims due `pending` rows (lease-based compare-and-set, one commit per delivery) and repeats steps 3–4 with the frozen config. This is also what recovers a fire whose first attempt was cut short by a crash or restart. |
| 6. Roll up | `app/core/outbox.py` | `apply_rollup_to_log` folds the per-channel states into the log row's `delivery_status`, `dispatched_to` and `failed_channels`. When every channel has failed terminally, the dedup claim and throttle reservation are released so the next identical fire is not swallowed. The first successful channel counts the fire exactly once (`gating.account_first_success`). A resolve and a settling worker can each write the rollup from an older snapshot; every worker tick re-rolls a notification left `pending` with no pending channel (`DeliveryWorker.repair_rollups`). |

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
- Dispatch is not asynchronous: `fire()` returns after the first attempt
  (or its 45 s budget), and `POST /v1/fire` waits for it. Incident notices
  (firing and recovery of an episode) pass `background_only` and leave the
  send to the delivery worker, but a plain rule fire is sent inline from the
  engine's loop, so a slow channel holds up every other rule for that long.
  Health reports a loop that has not come round for 180 s as engine
  `degraded` (`engine_stalled`, `app/core/health.py`); readiness deliberately
  stays `200`, because an unhealthy container would drop out of the reverse
  proxy's routing and take `/v1/fire` and the admin UI with it.

### Durable escalation

`EscalationService` queues one `Delivery` with `purpose=escalation` for an
eligible unacknowledged critical, and stamps `notifications_log.escalated_at`
in the same transaction. A conditional update prevents two sweeps from queuing
the same escalation. `escalated_at` now means **queued**, not delivered
(historical rows retain their old attempted-send meaning).

The escalation uses the ordinary delivery worker, frozen channel config/kind,
five-attempt limit and exponential backoff. Its transport identity is distinct
from the initial notification's and stable across retries. It expires after
one hour in the queue, so a long outage does not unleash old pages.
Escalation outcomes never change the initial delivery rollup, dedup/throttle
claims or rule fire counters. Both purposes can target the same channel.

Acknowledgement cancels queued escalation deliveries; a send already in flight
may complete, but no subsequent escalation retry is sent after acknowledgement.
Retention protects notifications with any pending delivery, including escalation.

### Rule incident lifecycle

Rules opt in with `incident_enabled`. `incidents.active_rule_id` is a nullable
unique FK: one open episode per rule, with resolved history. An instance of a
parametric rule (ADR-0005) keeps `active_rule_id` NULL and uses the unique
`active_source_key` external episodes use, as `rule:<id>:<instance>`
(`incidents.instance_key`); its `rule_name` is `name[instance]`. Rule-row locks
serialise opening against other opens and configuration edits. Incident locks
serialise ack/resolve. `app/core/incidents.py` commits transitions together with
outbox intents through `dispatcher.fire(background_only=True)`; no transport
runs in these transactions. Deduplication includes incident id and event, so
new episodes cannot coalesce onto old ones with identical values.

Recovery progress lives in `rule_state.recovery_match_count`, versioned by the
same `state_epoch` as the trigger streak. Missing/invalid data breaks both
streaks. Recovery only runs for open episodes and a true trigger wins. In the
hysteresis band, an open incident remains an active inhibitor. Reload awaits
session cleanup before the next evaluation.

Resolution cancels unleased firing deliveries; the worker also checks it after
reclaiming a lease. Cancellation uses `FOR UPDATE SKIP LOCKED` on delivery rows
before touching log rows, avoiding inversion with the worker's success-accounting
locks. In-flight sends can finish. Cancelled rollups release their admission and
cooldown reservations. Recovery notices account their own template cooldown but
do not increment the rule's alarm counter. See [incident semantics](INCIDENTS.md).

### `app/core/gating.py` — Gating pipeline

`gating.evaluate(gate_input, session)` runs the gates in order and returns
`allow(channels)` or `deny(reason)`; first deny wins. Order: enabled,
snoozed (type / rule → deny; channel → strip), throttled, delivery gate
(`below_gate`: the template's `gate_variable` is below `gate_min`),
quiet hours (strips channels; all stripped → `gated`). A test fire skips
throttle, delivery gate and quiet hours.

Persist is enforced by the engine, not here: the counter is
`rule_state.consecutive_match_count` (one row per rule). The
`throttle_state.persist_count` column is legacy and unused.

### `app/core/eval.py` — Safe expression eval

Wraps `simpleeval`:

- Names: the state cache, limited to the rule's `vars_extract` (plus the
  variables its expressions read) when set
- Functions: a fixed whitelist (numeric, list, string, time, sun, data age,
  history — `app/core/history.py`, ADR-0004: the store tracks what the enabled
  rules and computed formulas ask for, rebuilt at each engine / input reload)
  — see [EXPRESSION_LANGUAGE.md](EXPRESSION_LANGUAGE.md); a call to any other
  name is refused at write time. One evaluator per tick, built by
  `engine.settings_evaluator` with `ALERTD_TZ` and the place
  (`ALERTD_LATITUDE` / `ALERTD_LONGITUDE`) — the same for eval-now, validate
  and computed variables
- A default-deny AST allowlist checked before evaluation (and at write
  time): no attribute / method access, comprehensions, lambdas, slices or
  keyword arguments
- Bounded by size (2000 chars, 500 nodes, depth 40) and run-time caps on
  `**`, `*`, `%` — there is no timer

### `app/core/rendering.py` — Template rendering

Substitutes `{var}` and `%var%` placeholders (same semantics) with
`envelope.context[var]`, with pipe filters (`{x | fixed(1)}`). Missing
variables render as `[?var]` (visible to operator), not crash. The admin-UI
preview (`lib/render.js`) implements the same filters.

### `app/inputs/` — Input adapters (plug-ins)

Each adapter inherits `BaseInput`. Required:

- `__init__(self, *, name, config, on_value)` — `on_value(topic, payload, source_kind)`
- `async def start(self)` — begin streaming values (returns promptly)
- `async def stop(self)` — clean shutdown
- `def health(self) -> dict` — `{connected: bool, last_msg_ts: ...}`

Implementations:

- `MQTTSubscriber` (`mqtt.py`) — wraps `aiomqtt`, reads topic + JSONPath
- `HTTPPollInput` (`http_poll.py`) — asyncio-driven polling at configured interval
- `WebhookInput` (`webhook.py`) — passive: the static route
  `POST /v1/inputs/{id}/webhook` (`app/api/v1/inputs.py`) checks the input's
  token and hands the body to the running adapter, which fires `on_value`
- `SMSInboxInput` (`sms_inbox.py`) — a webhook input that receives SMS
  forwarded by an SMS gateway (e.g. a Teltonika router) as an HTTP POST (it does not poll) and
  normalises the gateway's JSON shape
- `AlertmanagerInput` (`alertmanager.py`) — receives Alertmanager v4 /
  Grafana alert groups on the same webhook route; pure parsing / template
  choice there, episodes via `app/services/alertmanager.py` → fire service

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

- `async def send(self, notif: Notification, config: dict, *, idempotency_key=None) -> SendResult`
- `async def healthcheck(self, config: dict) -> dict` — optional reachability probe
- `async def close(self) -> None` — optional cleanup for persistent resources

The channel manager and delivery worker handle retries, circuit breaker
state and `notifications_log` updates (see "Delivery path" above).
Channels are **simple**: send or fail.

Kinds: `ui` (WebSocket), `banner` (persistent UI banner), `telegram`,
`sms`, `email`, `push`, `webhook`, `mqtt`, `ntfy`, `gotify`, `pushover`. A channel that knows the
provider's id for a sent message returns it as `response["provider_ref"]`;
it is stored on the delivery (`deliveries.provider_ref`). Providers that keep a message alive
after sending (Pushover emergencies) are kept in sync by
`app/core/provider_lifecycle.py`: durable `lifecycle_commands` (cancel on
acknowledgement in Klopot) and a deduplicated `inbound_events` inbox
(acknowledgement in the provider's app), run by the provider-lifecycle
worker every 30 s. Two per-channel
guards wrap every send:

- `circuit_breaker.py` — opens after N consecutive failures
  (`circuit_breaker_threshold`), half-opens after
  `circuit_breaker_open_sec`; breaker state is written into the state
  cache every 30 s (so a rule can fire on a stuck-open breaker) and exported
  as `alertd_channel_breaker_state`.
- `rate_limiter.py` — token bucket per channel
  (`channels.rate_limit_per_min`) so a rule storm can't flood a
  destination.

The MQTT output owns persistent broker connections, independently of input
subscriptions. It reconnects with backoff and forwards failed notification
attempts to the normal outbox. Availability/LWT reports connectivity; a
separate heartbeat carries the last successful engine tick. The manager closes
output resources after the workers stop. See [MQTT_OUTPUT.md](MQTT_OUTPUT.md).

### Operational snapshots

`app/core/operations.py` supplies queue counts and ages, worker liveness,
Telegram/MQTT state and recent failures to the read-scoped `/v1/operations`
endpoint and Prometheus collector. Overdue delivery counts exclude active
leases. The admin Operations page refreshes this snapshot every ten seconds;
the portable dashboard and alert rules are in `contrib/`.
See [OPERATIONS.md](OPERATIONS.md).

### `app/services/config_io.py` — Config import / export semantics

A **pack** is a YAML mapping with any of `settings`, `inputs`, `templates`,
`channels`, `variables`, `rules`, `routes`, `schedules`. Rows are addressed by
**name** (template `type`, rule / variable / input / channel / schedule name,
route `template`→`channel`), never by database id, so a pack moves between
installations. `export_config` emits every section; `config_merge.export_selection`
emits a subset (sections, category, names, rule dependencies).

`import_config(session, pack, apply)` — used by `/v1/config/import`, the CLI
and, through `config_merge`, the item-by-item import:

1. **Validate the whole pack** before touching the DB (any error rejects all):
   schema / enums / settings whitelist / sizes / in-pack duplicates
   (`config_import_schema.validate_pack`, incl. emoji-only icons); variable →
   input exists (in the pack or the DB) and the variable config compiles;
   rule expressions pass the language contract; route ends exist; schedule
   template exists and the cron parses; entity caps count **net-new** names
   only. A rule pointing at an unknown template is a *warning* (it fires but
   dispatches nothing).
2. **Upsert in dependency order**, one transaction: settings → inputs →
   (flush) → templates → channels → (flush) → variables → rules → routes →
   schedules. Dry-run (`apply=False`) runs the same writes, then rolls back.
3. **An existing row is replaced field by field; a field the item omits gets
   its import default**, not the stored value (template `locale` `en`,
   `min_repeat_min` 30; rule `persist_n` 1, `eval_interval_sec` 10,
   `sort_order` 100; channel `rate_limit_per_min` 30; `enabled` true; config
   mappings replaced whole). `config_merge` compares through the same
   defaults, so a preview shows such changes.
4. **Masked values are never written over live ones**: an `env:UNKNOWN_*`
   placeholder or a shortened URL echo (`https://host/…`) from a masked
   export keeps the stored secret / URL (`_sanitize_imported_config`).
5. **Nothing is deleted**: rows absent from the pack stay as they are.
6. Side effects match the REST paths: a changed rule expression resets the
   persist streak (B-06); a template category reuses the existing spelling.
7. The API layer then audits `config.import` (names and counts only), commits
   and hot-reloads the input manager, the rule engine and pending schedules.

### `app/db/` — Persistence

MySQL 8 runtime, SQLAlchemy 2.0 ORM, async session per request. SQLite is used
only by the fast test harness; a separate MySQL gate verifies transaction and
locking semantics. Migrations run through Alembic on MySQL.
Connection pool bounded; transactions via `async with session.begin()`.

## Schema

See [`docs/SCHEMA.md`](SCHEMA.md) for the full DDL. Quick map:

| Table | Owner | Purpose |
|-------|-------|---------|
| `inputs` | admin | declared MQTT / HTTP-poll / webhook / SMS-inbox / Alertmanager sources |
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
| `deliveries` | engine | one row per notification × channel (the outbox) |
| `incidents` | engine | rule and external episodes |
| `push_subscriptions` | user | Web Push devices |
| `api_requests`, `delivery_attempts`, `system_events`, `activity_rules` | engine / admin | Activity log |

## Failure modes

| Failure | Mitigation |
|---------|------------|
| MQTT broker disconnect | The adapter reconnects with backoff; the input's health turns red (`/v1/health` → `degraded` for a critical input) and variables go stale (`stale_after_sec`), so rules that guard on `var_age()` stop matching. There is no built-in "broker down" alert: watch `/v1/health` or the `alertd_input_connected` metric |
| MySQL temporarily unreachable | API returns 503; readiness fails; pending deliveries stay in the outbox and are retried (5 attempts, given up after 1 h) |
| Channel adapter panics | Caught in the channel manager; recorded in `failed_channels` JSON; circuit breaker counts the failure; other channels still attempt |
| Expression error | Rule marked `last_eval_error`; auto-disabled after `ALERTD_EVAL_ERROR_DISABLE_THRESHOLD` (50) consecutive errors and the built-in `rule_auto_disabled` alert fires. A missing input is not counted |
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
