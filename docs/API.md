# alertd — API Reference

**Languages:** **English** · [Română](API.ro.md) ·
[← Back to README](../README.md)

Everything in alertd is driven by this HTTP API. The live,
auto-generated **OpenAPI / Swagger UI** is at **`/docs`** and the raw
schema at **`/openapi.json`** on any running instance — this document is
the hand-written companion with concepts and examples.

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
| `ack`   | `POST /v1/log/{id}/ack`, `POST /v1/snooze` |
| `admin` | Everything (implies all other scopes) |

Scopes are additive on a key (e.g. `["fire", "read", "ack"]`). `admin`
implies every scope. A `401` means "not authenticated"; a `403` means
"authenticated but missing the required scope".

---

## Error model

Errors are JSON. Handled errors use FastAPI's `detail`; a structured
error carries a `code`/`message`. Unexpected server errors return a
generic body plus an `X-Trace-Id` header for correlation (no internal
details are leaked).

```json
{ "detail": "Variable not found: battery.soc" }
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
  (default 100, max 500) and return `{ "items": [...], "total": N,
  "limit": L, "offset": O }`.
- **Timestamps:** ISO-8601 UTC.
- **Identifiers across config:** names/types (strings), not DB ids, so a
  config pack is portable between deployments.

---

## Health & version

```bash
curl https://host/v1/health      # service + DB + MQTT + per-channel/input
curl https://host/v1/version     # version string only, no infra probes
```

`/v1/health` (public) returns an overall `status` (`ok` / `degraded` /
`down`) and a `components` map. Use `/v1/version` for a cheap liveness
probe that never touches MySQL/MQTT.

```json
{ "status": "ok", "service": "alertd", "version": "1.7.0",
  "components": { "database": {"status":"ok"}, "mqtt": {"status":"ok","detail":"critical: 1/1 connected"} } }
```

## Metrics

```bash
curl https://host/v1/metrics     # Prometheus exposition format
```

Exposes `fires_total`, `dispatch_latency_ms`, `dispatch_failures_total`,
`rule_eval_duration_ms`, and more.

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
| `test` | bool | Default `false`. A test fire skips the *silencing* gates (throttle, quiet hours) but still records and dispatches; marked `is_test` in the log. |
| `source` | string | Optional free-text origin tag for the audit/log. |

```bash
curl -X POST https://host/v1/fire \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"type":"consumption_high","context":{"load_kw":5.4},"source":"node-red"}'
```

**Response** (`DispatchResult`)

```json
{ "id": "ntf_1794139677372_7fc1…",
  "dispatched": true,
  "channels": ["ui_default", "telegram_main"],
  "status": "sent",
  "suppressed_reason": null,
  "title": "Consumption high: 5.4 kW",
  "message": "Load crossed the threshold.",
  "severity": "warning" }
```

- `id` — the `notifications_log` row id. Always present (even when
  suppressed) so the caller can correlate.
- `dispatched` — `true` if the status is `sent` or `partial`.
- `channels` — channels that accepted the message on this attempt.
- `status` — see **[Delivery & outbox semantics](#delivery--outbox-semantics)**.
- `suppressed_reason` — why it was gated (e.g. `throttled`, `snoozed`,
  `quiet_hours`, `inhibited`, `pv_power`, `disabled`, `unknown_type`),
  or `null`.

If the `type` has no configured template, the fire is accepted, logged
as `unknown_type`, and nothing is dispatched (a safe no-op you can see
in the log).

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
`acknowledged` (bool), `is_test` (bool), `rule_id`, `search`, plus
`skip`/`limit`.

```bash
curl -H "X-API-Key: $KEY" \
  "https://host/v1/log?severity=critical&acknowledged=false&limit=20"
```

### `POST /v1/log/{id}/ack`

Acknowledge a notification (requires `ack`). ` GET /v1/log/stats`
returns counts over a time window.

---

## Snooze (mute)

### `POST /v1/snooze`

Mute by scope until a time. Requires `ack`.

```bash
curl -X POST https://host/v1/snooze \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"scope":"type","target":"consumption_high","until":"2026-12-01T00:00:00Z"}'
```

- `scope`: `type` (a template type; `"*"` = maintenance mode, mutes
  everything), `rule` (a rule id), or `channel` (a channel name —
  strips just that destination).
- `GET /v1/snooze` lists active snoozes; `DELETE /v1/snooze/{id}` ends
  one.

---

## Live state & streams

### `GET /v1/state`

A snapshot of the live variable cache (current value, age, source) —
useful for debugging what rules see. Requires `read`.

### WebSocket `GET /v1/stream/notifications`

Live feed of dispatched notifications (the UI channel). Auth with
`?api_key=...` (browsers can't set WS headers) or the session cookie.

### WebSocket `GET /v1/stream/state`

Live feed of every variable update (debug firehose).

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
- **`POST /v1/config/validate`** — validate a YAML pack without writing;
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

## Form metadata

### `GET /v1/meta/kinds`

Returns the field schemas for every input/channel/variable kind (what
the admin UI builds its forms from) plus webhook presets (Slack,
Discord, Teams, …). Read this to know which config fields a given kind
accepts.

## Settings & audit

- **`GET` / `PATCH /v1/settings`** — runtime tunables (retention
  windows, breaker thresholds, timezone…). Note: some operational values
  are read from the environment at startup — see [Deploy](DEPLOY.md).
- **`GET /v1/audit`** — paged history of admin actions (who changed
  what, with before/after and a trace id). Filters: `action`,
  `resource_kind`, `resource_id`, `actor`.

---

## Configuration resources (CRUD)

Each of these is a standard REST collection: `GET` (list, paginated),
`POST` (create), `GET /{id|name}` (one), `PATCH /{id|name}` (update),
`DELETE /{id|name}`. All writes require `admin` and are audited. Field
schemas come from `GET /v1/meta/kinds`.

| Collection | What it is |
|------------|------------|
| `/v1/inputs` | Declared sources: MQTT / HTTP-poll / webhook / sms_inbox. Plus `GET /{id}/health` and `POST /{id}/restart`. |
| `/v1/variables` | Named values extracted from inputs (`mqtt`, `aggregate`, `constant`, `computed`, `schedule`). |
| `/v1/templates` | Per-type title/message/severity/icon, cooldown (`min_repeat_min`), quiet hours, optional `require_pv_kw` gate, `category`. |
| `/v1/channels` | Delivery destinations (telegram/sms/email/push/webhook/ui) + rate limit + quiet hours. `POST /{id}/breaker/reset` reopens a tripped breaker. |
| `/v1/rules` | Condition expression + `persist_n` + eval interval + `inhibited_by` + operator-visible trigger summary. |
| `/v1/schedules` | Cron-driven fires of a template type. |
| `/v1/api_keys` | Caller authentication. Create returns the key once; `POST /{id}/rotate` issues a new secret with a grace window. |

**Create examples**

```bash
# A channel (UI WebSocket — no secrets)
curl -X POST https://host/v1/channels -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"ui_default","kind":"ui","config":{}}'

# A template
curl -X POST https://host/v1/templates -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"consumption_high","severity":"warning",
       "title_template":"Consumption high: {load_kw} kW",
       "message_template":"Load crossed the threshold.","min_repeat_min":30}'

# Route the template to the channel (via a config import pack)
# A rule that fires it from a live variable
curl -X POST https://host/v1/rules -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"consumption_high_rule","template_type":"consumption_high",
       "condition_expr":"load_kw > 5","persist_n":3,"eval_interval_sec":10}'
```

> **Template → channel routing** (`template_channels`, with per-route
> `severity_min` and `channel_overrides`) is managed through the config
> import/export API — there is no standalone per-route REST endpoint
> yet.

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
