# Schema reference

Authoritative DDL for the alertd MySQL schema. Updated alongside
Alembic migrations. The DDL below is conceptual (MySQL 8.0
dialect); the actual column types and indexes live in
`app/db/models.py` and the Alembic versions (all shipped — see the
Migrations table at the end).

## Conventions

- All `id` columns are `BIGINT AUTO_INCREMENT PRIMARY KEY` unless
  otherwise noted.
- Timestamps are stored in UTC and rendered in local time. Actual models
  generally use `DATETIME` with column-specific defaults; the conceptual DDL
  below also uses `TIMESTAMP`. Models and migrations define the exact types
  and defaults.
- All JSON columns are `JSON` type (MySQL 8.0 native, validated
  on insert).
- Foreign keys use `ON DELETE` semantics documented per table.
- All "lifecycle" columns (`enabled`, `created_at`, `updated_at`)
  are present unless the table is purely runtime state (e.g.,
  `rule_state`).
- Names: snake_case, plural for entity tables, singular for state
  tables.
- Text columns use `utf8mb4_unicode_ci`. That collation ignores case **and
  compares every 4-byte emoji as equal**, so `GROUP BY icon`,
  `WHERE icon = '🚀'` or `GROUP BY category` silently merge different values.
  Use `BINARY col` when counting or matching emoji or exact spellings.

## Entity-relationship overview

```
inputs ──┐
         ├── variables
mqtt+    ├── (computed vars reference other variables by name)
http+    │
webhook+ │
sched+   │
sms+     │
email+   │
         │
templates ── template_channels ── channels
   │            (M:N)             telegram/sms/email/push/...
   │
rules ──── notifications_log ── (rule_id FK, optional)
   │
   └── rule_state (1:1 runtime)

snooze (independent — scope refers to type/rule/channel)
api_keys (independent)
audit_log (independent — references actors only by name)
schedules ── (schedule rows fire alerts via internal events)
settings (single-row)
user_prefs (future, multi-user)
```

## Table reference

### `inputs`

Declared external sources of values.

```sql
CREATE TABLE inputs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    kind ENUM('mqtt','http_poll','webhook','schedule',
              'sms_inbox','email_imap','alertmanager') NOT NULL,
    config JSON NOT NULL,
        -- Per-kind shape (validated at write time by Pydantic):
        -- mqtt: {host, port, username, password_ref, client_id, qos}
        -- http_poll: {url, method, headers, interval_sec, json_path, timeout_sec}
        -- webhook: {auth_required, auth_token | auth_token_ref}
        -- alertmanager: {auth_required, auth_token | auth_token_ref, type_label, …}
        -- schedule: {cron}
        -- sms_inbox: {auth_required, auth_token | auth_token_ref} (receives forwarded SMS)
        -- inbound kinds: a token is required unless auth_required is false (0041)
        -- email_imap: {host, port, username, password_ref, mailbox, filter}
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);
```

**`config` secrets contract.** No plaintext credentials in `config`.
Sensitive fields use the suffix `_ref` and store an environment
variable name. Resolution at runtime: `os.environ[ref]`. Examples:

```json
{"host": "broker.local", "port": 1883,
 "username": "alertd", "password_ref": "MQTT_PASSWORD"}
```

The admin UI shows `_ref` fields as plain text inputs (the env-var
name is not a secret); the actual env-var values come from the
deployment.

**Enforcement (2026-11-07).** `app/secrets_registry.py` lists, per
resource kind, which `config` keys are literal secrets. Every read
path (`GET /v1/inputs*`, `GET /v1/channels*`, `audit_log.before/after`)
masks them as `"<redacted>"` and exposes `secret_fields_set`
(`{"password": "env:ALERTD_MQTT_PASSWORD" | "literal"}`); `PATCH`
keeps a stored secret when the field is omitted / `null` / the masked
echo, clears it on `""`, replaces it otherwise. A literal secret can
still be stored (development convenience) but is never returned.

### `variables`

Named values exposed to rule expressions and template substitution.

```sql
CREATE TABLE variables (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,    -- e.g., "disk.used_pct"
    source ENUM('mqtt','aggregate','computed','constant','schedule') NOT NULL,
    input_id BIGINT NULL,                  -- nullable for computed/constant
    config JSON NOT NULL,
        -- Per-source shape:
        -- mqtt: {topic, json_path?, type, stale_after_sec}
        -- aggregate: {topics: [...], aggregate: 'sum'|'avg'|'max'|'min', type}
        -- computed: {formula, type}        -- formula is simpleeval expression
        -- constant: {value}
        -- schedule: {schedule: [{start, end, value}]}
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (input_id) REFERENCES inputs(id) ON DELETE SET NULL,
    INDEX idx_var_source (source),
    INDEX idx_var_enabled (enabled)
);
```

### `templates`

Per-type rendering definition (one template per type).

```sql
CREATE TABLE templates (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    type VARCHAR(64) NOT NULL UNIQUE,
    severity ENUM('info','warning','critical') NOT NULL,
    icon VARCHAR(8),                           -- an emoji; validated by the API
    title_template TEXT NOT NULL,
    message_template TEXT,
    runbook_url VARCHAR(500),
    description TEXT,
    locale VARCHAR(8) NOT NULL DEFAULT 'en',
    -- Behavior tuning at template scope (rule overrides where applicable)
    min_repeat_min INT NOT NULL DEFAULT 30,    -- cooldown
    gate_variable VARCHAR(128),                -- delivery gate: variable read (0030)
    gate_min FLOAT,                            -- deliver only while gate_variable >= gate_min
    quiet_hours JSON,                          -- {"sms":"22-07", ...}
    category VARCHAR(32),                      -- UI grouping (migration 0003)
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tmpl_severity (severity),
    INDEX idx_tmpl_enabled (enabled),
    INDEX ix_templates_category (category)
);
```

- `icon`: an emoji (≥ 1 pictographic symbol, no letters / digits / `?`),
  checked by `app/utils/icons.py` on create, update and config import. The
  column itself accepts any text, so rows written before that check may hold
  mis-encoded values; the admin UI flags them.
- `category`: free text, NULL = uncategorized. Case variants are one category:
  the API stores a new value with the spelling already in use, and the UI
  groups case-insensitively.

### `rules`

Trigger logic — one template type can have many rules.

```sql
CREATE TABLE rules (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    template_type VARCHAR(64) NOT NULL,
        -- soft FK: matches templates.type. We don't enforce a hard FK so
        -- a template can be deleted without cascading rule deletions
        -- (rule auto-disables instead — visible to operator).
    -- Trigger logic (THE KEY THING)
    condition_expr TEXT NOT NULL,
    incident_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    recovery_expr TEXT,
    recovery_persist_n INT NOT NULL DEFAULT 1,
    resolved_template_type VARCHAR(64),
    persist_n INT NOT NULL DEFAULT 1,
    eval_interval_sec INT NOT NULL DEFAULT 10,
    -- Variables to pass to template (subset of state cache)
    vars_extract JSON NOT NULL DEFAULT '[]',
    -- Documentation FOR USER (visible in UI)
    trigger_summary VARCHAR(500),
    trigger_logic_md TEXT,
    -- Lifecycle
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 100,
    last_evaluated_at TIMESTAMP,
    last_fired_at TIMESTAMP,
    fire_count_lifetime BIGINT NOT NULL DEFAULT 0,
    last_eval_error TEXT,
    consecutive_eval_errors INT NOT NULL DEFAULT 0,
    inhibited_by JSON NOT NULL DEFAULT '[]',   -- rule names that suppress this one while active
    state_epoch INT NOT NULL DEFAULT 0,        -- bumped on reconfiguration (audit B-06)
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_rules_template (template_type),
    INDEX idx_rules_enabled (enabled, sort_order)
);
```

- `last_eval_error`: the last evaluation message. A message starting with
  `missing input:` means a dotted variable had no value (the rule is waiting,
  not broken) and is **not** counted in `consecutive_eval_errors`. Any
  successful evaluation clears it. The API derives `eval_status`
  (`ok` / `no_data` / `error`) from these two columns — see
  [API.md](API.md#rule-evaluation-status).
- `consecutive_eval_errors`: real expression failures in a row; at
  `ALERTD_EVAL_ERROR_DISABLE_THRESHOLD` the rule auto-disables.

### `rule_state`

Runtime state per rule (fast counter, separate from config so admin
edits don't lose ramp-up progress).

```sql
CREATE TABLE rule_state (
    rule_id BIGINT PRIMARY KEY,
    consecutive_match_count INT NOT NULL DEFAULT 0,
    recovery_match_count INT NOT NULL DEFAULT 0,
    last_match_at TIMESTAMP,
    last_eval_result JSON,             -- last evaluated context for debugging
    state_epoch INT NOT NULL DEFAULT 0,  -- the rules.state_epoch the streak was counted under
    FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE CASCADE
);
```

### `channels`

Output destination declarations.

```sql
CREATE TABLE channels (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    kind ENUM('ui','banner','telegram','sms','email','push','webhook','mqtt','ntfy','gotify','pushover') NOT NULL,
    config JSON NOT NULL,
        -- Per-kind shape (secrets via _ref):
        -- ui: {} (broadcasts via WebSocket; no config)
        -- banner: {} (in-app banner; no config)
        -- telegram: {bot_token_ref, chat_id, parse_mode}
        --           + opt-in inline_actions and actor policy (0026)
        -- mqtt: {topic_template, qos, retain, host, port, username_ref,
        --        password_ref, tls, instance_id, availability_topic, heartbeat_topic}
        -- ntfy: native priority/tag/click config (0028); see API.md
        -- sms: {provider: http|twilio|teltonika|kurier, phone, max_chars} +
        --   http: {url, method, content_type, body_template, auth_kind,
        --          auth_header, auth_value_ref, health_url}
        --   twilio: {account_sid, auth_token_ref, from_number}
        --   teltonika: {router_url, username, password_ref, modem}
        --   kurier: {kurier_url, api_key_ref, dedup_key, ttl_seconds, max_segments,
        --            watchdog, watchdog_timeout_sec, watchdog_to}
        --            (ADR-0003; no migration — config JSON)
        --   (pre-0031 {gateway_url, gateway_api_key_ref} is converted on write)
        -- email: {smtp_host, smtp_port, username, password_ref,
        --         from, to: [...], use_tls}
        -- push: {vapid_public_ref, vapid_private_ref, subject}
        -- webhook: {url, method, headers, body_template,
        --           auth: {kind, value_ref}}
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    rate_limit_per_min INT NOT NULL DEFAULT 30,
    quiet_hours JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_channel_kind (kind),
    INDEX idx_channel_enabled (enabled)
);
```

**Built-in channels (auto-seeded on first boot):**
- `ui_default` (kind=`ui`) — WebSocket broadcast to all listeners
- `banner_default` (kind=`banner`) — in-app banner

### `template_channels`

Many-to-many routing of templates to channels with optional per-route
overrides.

```sql
CREATE TABLE template_channels (
    template_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    severity_min ENUM('info','warning','critical')
        NOT NULL DEFAULT 'info',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    channel_overrides JSON,              -- per-route config tweaks
    PRIMARY KEY (template_id, channel_id),
    FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);
```

### `incidents`

Durable rule episodes (migration `0025`). `id` is a `VARCHAR(64)` primary key.
`rule_id` and nullable unique `active_rule_id` reference `rules.id` with
`ON DELETE SET NULL`. Resolution clears `active_rule_id`, allowing another
episode for that rule. Multiple historical nulls are allowed.

Snapshots: `rule_name VARCHAR(128)`, `template_type VARCHAR(64)`, optional
`resolved_template_type VARCHAR(64)`, severity enum, `title VARCHAR(255)`,
`opening_context JSON` and optional `resolution_context JSON`. Lifecycle:
`opened_at`, nullable `resolved_at`, nullable `acknowledged_at` (DATETIME),
`acknowledged_by VARCHAR(64)` and `resolution_reason VARCHAR(500)`.
State is derived from `resolved_at`; acknowledgement is independent.
Indexes cover `(resolved_at, opened_at)` and `(rule_id, opened_at)`.

External episodes (migration `0028`): `source_kind VARCHAR(32) NOT NULL
DEFAULT 'rule'` (`rule` / `fire` / `alertmanager`), `source_key VARCHAR(191)`
(indexed episode identity), `active_source_key VARCHAR(191) UNIQUE` (set while
open, cleared on resolution — like `active_rule_id`; both `COLLATE utf8mb4_bin`
since `0036`, so keys are case-sensitive) and `source_started_at
DATETIME` (the source's start, e.g. Alertmanager `startsAt`). For these rows
`rule_id` is NULL and `rule_name` holds the source's name (the alertname, the
idempotency key). See [INCIDENTS.md](INCIDENTS.md#external-episodes).

> Never take a locking read (`SELECT … FOR UPDATE`) on `active_source_key`
> for a key that may not exist and then INSERT it: on MySQL the gap locks of
> two concurrent callers deadlock and the whole transaction is rolled back.
> `fire_service._active` reads plainly, then locks by primary key.

### `notifications_log`

Canonical history of every fire (dispatched + suppressed).

```sql
CREATE TABLE notifications_log (
    id VARCHAR(64) PRIMARY KEY,         -- "ntf_<unix_ms>_<type>"
    template_id BIGINT,                  -- nullable: unknown_type fires
    rule_id BIGINT,                      -- nullable: external /v1/fire
    incident_id VARCHAR(64),              -- FK incidents.id ON DELETE SET NULL
    incident_event VARCHAR(16),           -- firing / resolved; NULL for legacy
    type VARCHAR(64) NOT NULL,
    severity ENUM('info','warning','critical') NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT,                         -- rendered; cut to 65,535 UTF-8 bytes (fit_message)
    vars_payload JSON,
    -- Dispatch
    fired_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dispatched_to JSON NOT NULL DEFAULT '[]',
    failed_channels JSON NOT NULL DEFAULT '{}',
    suppressed_reason ENUM(
        'disabled','snoozed','throttled','persist','gated',
        'duplicate','unknown_type','inhibited','below_gate'
    ),
    delivery_status ENUM(
        'sent','partial','failed','suppressed','pending','cancelled'
    ),                                   -- settled rollup of the deliveries
    escalated_at TIMESTAMP,
    is_test BOOLEAN NOT NULL DEFAULT FALSE,
    context_hash VARCHAR(16),            -- dedup admission key (audit R01)
    success_counted BOOLEAN NOT NULL DEFAULT FALSE,
    dispatch_latency_ms INT,
    -- User actions
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(64),
    snoozed_until TIMESTAMP,
    -- Audit / observability
    source VARCHAR(191),                 -- "node-red", "internal-engine", caller name
    trace_id VARCHAR(40),
    FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE SET NULL,
    FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE SET NULL,
    INDEX idx_log_fired (fired_at DESC),
    INDEX idx_log_type (type, fired_at DESC),
    INDEX idx_log_unack (acknowledged_at, fired_at DESC),
    INDEX idx_log_severity (severity, fired_at DESC),
    INDEX idx_log_suppressed (suppressed_reason),
    INDEX idx_log_rule (rule_id, fired_at DESC)
);
```

### `deliveries`

Transactional outbox, with one row per `(notification_id, channel, purpose)`.
The purpose is `notification` (default, including pre-0024 rows) or `escalation`.
Escalation state is tracked independently from the initial notification rollup.

```sql
CREATE TABLE deliveries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    notification_id VARCHAR(64) NOT NULL,
    channel VARCHAR(64) NOT NULL,
    purpose VARCHAR(16) NOT NULL DEFAULT 'notification',
    state ENUM('pending','sent','failed','cancelled') NOT NULL,
    attempts INT NOT NULL,
    next_attempt_at DATETIME,
    idempotency_key VARCHAR(130) NOT NULL,
    channel_overrides JSON,
    effective_config JSON,
    effective_kind VARCHAR(32),
    last_error VARCHAR(500),
    action_keyboard JSON,               -- Telegram callback keyboard, stored before sending (0026)
    provider_ref VARCHAR(255),          -- provider's message id, e.g. "ntfy:<id>" (0028)
    lease_until DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (notification_id) REFERENCES notifications_log(id) ON DELETE CASCADE,
    UNIQUE KEY uq_delivery_notif_channel_purpose (notification_id, channel, purpose),
    INDEX ix_delivery_due (state, next_attempt_at),
    INDEX ix_delivery_idempotency_key (idempotency_key),  -- looked up on every send (0035)
    INDEX ix_delivery_provider_ref (provider_ref)         -- Pushover receipt poll prefix range (0038)
);
```

`cancelled` denotes an acknowledged escalation or a firing delivery stopped
by incident resolution. A wholly cancelled notification rolls up to the new
`notifications_log.delivery_status='cancelled'` enum value.
Frozen destination fields can contain credentials and are never included in the
log API. `notifications_log.escalated_at` records durable escalation enqueue;
historical rows record the previous direct send attempt.

### `throttle_state`

Last-fire tracker per type — single row per template type.

```sql
CREATE TABLE throttle_state (
    type VARCHAR(64) NOT NULL,
    is_test BOOLEAN NOT NULL DEFAULT FALSE,   -- real and test fires throttle apart (0040)
    last_fired_at TIMESTAMP,
    persist_count INT NOT NULL DEFAULT 0,
    persist_last_seen TIMESTAMP,
    reserved_at TIMESTAMP,               -- cooldown admission (audit B-10)
    reserved_by VARCHAR(64),             -- the notification holding the reservation
    PRIMARY KEY (type, is_test)
);
```

### `snooze`

Temporary mute. Scope = `type` / `rule` / `channel`.

```sql
CREATE TABLE snooze (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    scope ENUM('type','rule','channel') NOT NULL,
    target VARCHAR(128) NOT NULL,
        -- type name, rule.id, channel.id (string-encoded for ints)
    until TIMESTAMP NOT NULL,
    reason TEXT,
    created_by VARCHAR(64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_snooze_scope_target (scope, target),
    INDEX idx_snooze_until (until)
);
```

### `schedules`

Cron-driven fires.

```sql
CREATE TABLE schedules (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    cron_expr VARCHAR(64) NOT NULL,
    template_type VARCHAR(64) NOT NULL,
    context JSON NOT NULL DEFAULT '{}',     -- vars passed to template
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_fired_at TIMESTAMP,
    next_fire_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_sched_next (next_fire_at, enabled)
);
```

### `api_keys`

Service-to-service auth.

```sql
CREATE TABLE api_keys (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    key_hash VARCHAR(255) NOT NULL,         -- bcrypt(plaintext, cost=12)
    key_prefix VARCHAR(8) NOT NULL,         -- first 8 chars for UI/audit
    key_digest VARCHAR(64) NULL,            -- sha256 hex of a generated key: lookup without bcrypt.
                                            -- NULL until first use for keys issued before 0034,
                                            -- always NULL for operator-chosen keys (bcrypt only)
    scopes JSON NOT NULL DEFAULT '["fire"]',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMP NULL,
    last_used_at TIMESTAMP NULL,
    last_used_ip VARCHAR(45),
    allowed_cidrs JSON NULL,                -- source allowlist (normalised IPs/CIDRs); NULL/[] = any (0042)
    rate_limit_per_min INT NULL,            -- requests a minute (GCRA, in process); NULL = no limit (0043)
    allowed_types JSON NULL,                -- types / patterns it may fire (/v1/fire); NULL/[] = every type (0044)
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rotated_from_id BIGINT NULL,
    INDEX idx_apikey_prefix (key_prefix),
    UNIQUE INDEX uq_api_keys_key_digest (key_digest),
    INDEX idx_apikey_enabled (enabled),
    FOREIGN KEY (rotated_from_id) REFERENCES api_keys(id) ON DELETE SET NULL
);
```

### `audit_log`

Admin action history (separate from `notifications_log`).

```sql
CREATE TABLE audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_kind ENUM('api_key','jwt','system','user') NOT NULL,
    actor_id BIGINT,                        -- api_keys.id or user.id
    actor_name VARCHAR(64),
    action VARCHAR(64) NOT NULL,
        -- "rule.create", "rule.update", "rule.delete", "channel.create", ...
    resource_kind VARCHAR(32),
    resource_id VARCHAR(191),
    before JSON,
    after JSON,
    trace_id VARCHAR(40),
    INDEX idx_audit_ts (ts DESC),
    INDEX idx_audit_actor (actor_id, ts DESC),
    INDEX idx_audit_action (action, ts DESC),
    INDEX idx_audit_resource (resource_kind, resource_id)
);
```

### Activity log (`delivery_attempts`, `api_requests`, `activity_rules`, `system_events`)

Migration 0032 — design and policy in [ACTIVITY_LOG.md](ACTIVITY_LOG.md).
Written off the hot path by `app.core.activity` (batched), swept by retention.
Outcome / event / action values are plain strings, so adding one needs no
migration.

```sql
CREATE TABLE delivery_attempts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    delivery_id BIGINT,                     -- deliveries.id ON DELETE CASCADE; NULL for a channel test
    notification_id VARCHAR(64),
    channel VARCHAR(64) NOT NULL,
    kind VARCHAR(16) NOT NULL,              -- alert | escalation | test
    attempt_no INT NOT NULL DEFAULT 1,
    started_at DATETIME NOT NULL,
    duration_ms INT NOT NULL DEFAULT 0,
    outcome VARCHAR(16) NOT NULL,           -- sent | deferred | failed | permanent | timeout
    http_status INT,
    retry_after_sec INT,
    provider_ref VARCHAR(255),
    error VARCHAR(500),
    exchange JSON,                          -- [{method, url, status, duration_ms, request_body, response_body, response_headers, error}]
    INDEX ix_attempts_delivery (delivery_id),
    INDEX ix_attempts_notification (notification_id),
    INDEX ix_attempts_channel_ts (channel, started_at),
    INDEX ix_attempts_ts (started_at)
);
```

```sql
CREATE TABLE api_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts DATETIME NOT NULL,
    method VARCHAR(8) NOT NULL,
    route VARCHAR(191) NOT NULL,            -- template, e.g. /v1/inputs/{input_id}/webhook
    path VARCHAR(500) NOT NULL,             -- with the query string, redacted
    status INT NOT NULL,
    duration_ms INT NOT NULL DEFAULT 0,
    actor_kind VARCHAR(16),                 -- api_key | user
    actor_name VARCHAR(64),
    api_key_id BIGINT,
    client_ip VARCHAR(45),
    user_agent VARCHAR(255),
    trace_id VARCHAR(40),
    request_body MEDIUMTEXT,                -- redacted; policy: ACTIVITY_LOG.md
    response_body TEXT,
    expires_at DATETIME NOT NULL,           -- ts + rule keep_days, else ts + log_retention_days
    rule_id BIGINT,                         -- the activity rule that matched
    INDEX ix_api_requests_ts (ts),
    INDEX ix_api_requests_expires (expires_at),
    INDEX ix_api_requests_route_ts (route, ts),
    INDEX ix_api_requests_status_ts (status, ts),
    INDEX ix_api_requests_trace (trace_id)
);
```

```sql
CREATE TABLE activity_rules (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    position INT NOT NULL DEFAULT 100,      -- lower first; the first match wins
    match_method VARCHAR(8),                -- NULL = any
    match_path VARCHAR(191) NOT NULL DEFAULT '*',  -- glob on the path
    match_status VARCHAR(8),                -- NULL | 2xx … | an exact code
    match_actor VARCHAR(64),                -- glob on the key / user name
    match_ip VARCHAR(64),                   -- glob on the client IP
    action VARCHAR(8) NOT NULL DEFAULT 'keep',      -- keep | ignore (counted only)
    keep_days INT,                          -- NULL = log_retention_days
    request_body VARCHAR(8) NOT NULL DEFAULT 'auto', -- auto | never | errors | always
    response_body VARCHAR(8) NOT NULL DEFAULT 'auto',
    hits BIGINT NOT NULL DEFAULT 0,
    last_hit_at DATETIME,
    last_ip VARCHAR(45),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_activity_rules_position (position)
);
```

```sql
CREATE TABLE system_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts DATETIME NOT NULL,
    source_kind VARCHAR(16) NOT NULL,       -- input | rule | channel | push_device
    source_id BIGINT,
    source_name VARCHAR(128) NOT NULL,
    event VARCHAR(32) NOT NULL,             -- connected | disconnected | error | recovered | eval_error | eval_recovered | auto_disabled | breaker_open | breaker_closed | device_removed | device_disabled
    detail VARCHAR(500),
    INDEX ix_system_events_ts (ts),
    INDEX ix_system_events_source (source_kind, source_id, ts)
);
```

### `push_subscriptions` (migration 0033)

One row per browser / installed app that receives Web Push
([WEB_PUSH.md](WEB_PUSH.md)). Registered by the device itself
(`POST /v1/push/subscriptions`, signed-in session), managed by an admin. A
404 / 410 from the push service deletes the row; 20 failures in a row pause
it (`enabled = FALSE`). `p256dh` / `auth` are the device's public encryption
keys — not secrets, never shown by the API or written to the audit log.

```sql
CREATE TABLE push_subscriptions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    endpoint VARCHAR(1024) NOT NULL,        -- push-service URL (allowlisted hosts only)
    endpoint_hash VARCHAR(64) NOT NULL,     -- sha256(endpoint), the unique key
    p256dh VARCHAR(255) NOT NULL,
    auth VARCHAR(255) NOT NULL,
    label VARCHAR(100) NOT NULL,            -- "iPhone · Safari", editable
    min_severity ENUM('info','warning','critical') NOT NULL DEFAULT 'warning',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(64),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_success_at DATETIME,
    last_failure_at DATETIME,
    last_error VARCHAR(500),
    consecutive_failures INT NOT NULL DEFAULT 0,
    paused_reason VARCHAR(16),              -- service / operator; NULL while enabled (0037)
    UNIQUE KEY uq_push_subscriptions_endpoint_hash (endpoint_hash)
);
```

### `settings`

Single-row global config (template overrides win where applicable).

```sql
CREATE TABLE settings (
    id INT PRIMARY KEY DEFAULT 1,
    log_retention_days INT NOT NULL DEFAULT 90,
    audit_retention_days INT NOT NULL DEFAULT 365,
    idempotency_window_sec INT NOT NULL DEFAULT 300,
    default_eval_interval_sec INT NOT NULL DEFAULT 10,
    circuit_breaker_threshold INT NOT NULL DEFAULT 3,
    circuit_breaker_open_sec INT NOT NULL DEFAULT 60,
    bridge_max_queue INT NOT NULL DEFAULT 100,
    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CHECK (id = 1)
);
```

### `admin_users`, `admin_sessions`, `login_attempts` (migration 0008)

Human authentication for the admin UI — see `docs/AUTH_MODEL.md`
"Browser sessions".

```sql
CREATE TABLE admin_users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,          -- argon2id PHC string
    role VARCHAR(16) NOT NULL DEFAULT 'admin',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    password_changed_at DATETIME NULL,
    last_login_at DATETIME NULL,
    last_login_ip VARCHAR(45) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE admin_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,          -- sha256(cookie token); the token itself is never stored
    csrf_token CHAR(64) NOT NULL,                 -- echoed by the SPA in X-CSRF-Token
    created_at DATETIME NOT NULL,                 -- naive UTC
    last_seen_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,                 -- min(created+MAX_DAYS, last_seen+IDLE_HOURS)
    revoked_at DATETIME NULL,
    ip VARCHAR(45) NULL,
    user_agent VARCHAR(255) NULL,
    INDEX ix_sessions_user_active (user_id, revoked_at, expires_at),
    INDEX ix_sessions_last_seen (last_seen_at)            -- retention (0039)
);

CREATE TABLE login_attempts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts DATETIME NOT NULL,
    username VARCHAR(64) NULL,
    ip VARCHAR(45) NULL,                    -- the address's unit: IPv4 as is, IPv6 its /64 (1.2)
    success BOOLEAN NOT NULL,
    INDEX ix_attempts_user_ts (username, ts),
    INDEX ix_attempts_ip_ts (ip, ts),
    INDEX ix_login_attempts_ts (ts)                       -- retention (0039)
);
```

`audit_log.actor_kind` gained the value `user` in the same migration.
Retention: `login_attempts` and revoked/expired sessions older than
`ALERTD_AUTH_HISTORY_DAYS` (30) are pruned hourly; live sessions are
never pruned (expiry is enforced at resolve time).

### `user_prefs` (future)

Reserved for future multi-user support — silent in v1.

```sql
CREATE TABLE user_prefs (
    user_id VARCHAR(64) PRIMARY KEY,
    settings JSON NOT NULL DEFAULT '{}',
    -- e.g., {"channel_overrides": {"sms": false}, "quiet_hours": ...}
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);
```

## Migrations

All shipped. Migrations run automatically at container startup
(fail-fast) — see `docs/DEPLOY.md`.

| Revision | Status | Description |
|----------|--------|-------------|
| `0001` | ✅ shipped (S1) | empty bootstrap so `alembic_version` exists |
| `0002` | ✅ shipped (S2) | full schema as defined above |
| `0003` | ✅ shipped (2026-05-11) | `templates.category` — UI grouping |
| `0004` | ✅ shipped (2026-05-17) | `audit_log.ts` normalized to UTC at rest (serialized with `Z` suffix) |
| `0005`–`0023` | ✅ shipped (2026-07 – 2026-11-12) | `notifications_log` UTC, rule inhibition, escalation, admin auth (`0008`), delivery status, suppressed reason, the delivery outbox (`0011`) and its overrides / lease / effective config / effective kind, wider identifiers, context hash, `dedup_claims` (`0016`), `schedule_occurrences` (`0018`), success counting, `variables.input_id` `RESTRICT`, rule state epoch, throttle reservation. One file each in `alembic/versions/` |
| `0024` | Added (2026-11-13) | Delivery purpose, separate initial/escalation uniqueness, cancelled escalations; existing deliveries remain `notification` |
| `0025` | Added (2026-11-13) | Optional incident/recovery config, recovery streak, incidents, notification links and cancelled notification status |
| `0026` | Added (2026-11-14) | Telegram callback capabilities, inbox/cursor, local commands, provider receipts and cleanup commands; forward-only |
| `0027` | Added (2026-11-14) | Add `mqtt` to channel kinds; existing channels and routes unchanged; forward-only |
| `0028` | Added (2026-11-14, 1.1.0) | External episodes on `incidents`, `deliveries.provider_ref`, `alertmanager` input and `ntfy` channel kinds; forward-only |
| `0029` | Added (2026-11-14, 1.1.0) | `lifecycle_commands`, `inbound_events`; `gotify` and `pushover` channel kinds; forward-only |
| `0030` | Added (2026-11-15, 1.1.0) | Generic delivery gate: `templates.gate_variable` + `gate_min` replace the fixed `require_pv_kw` variable; existing templates converted; forward-only |
| `0031` | Added (2026-11-15, 1.1.0) | SMS channel providers (`http` / `twilio` / `teltonika`); pre-0031 SMS configs converted to provider `http`; forward-only |
| `0032` | Added (2026-11-15, 1.1.0) | Activity log: `delivery_attempts`, `api_requests`, `activity_rules`, `system_events`; forward-only |
| `0033` | Added (2026-11-15, 1.1.0) | `push_subscriptions` (Web Push devices); forward-only |
| `0034` | Added (2026-11-15, 1.1.0) | `api_keys.key_digest` (sha256 of a generated key, unique): key lookup without bcrypt; filled on first use for existing keys; forward-only |
| `0035` | Added (2026-11-15, 1.1.0) | Index `ix_delivery_idempotency_key` on `deliveries (idempotency_key)`: the per-send lookup was a full table scan; forward-only |
| `0036` | Added (2026-11-15, 1.1.0) | `incidents.source_key` / `active_source_key` collated `utf8mb4_bin` on MySQL: episode keys are case-sensitive; forward-only |
| `0037` | Added (2026-11-15, 1.1.0) | `push_subscriptions.paused_reason` (`service` / `operator`): who paused a device, recorded instead of inferred; existing paused rows classified once; forward-only |
| `0038` | Added (2026-11-15, 1.1.0) | Index `ix_delivery_provider_ref` on `deliveries (provider_ref)`: the per-minute Pushover receipt poll scanned the delivery history; forward-only |
| `0039` | Added (2026-11-15, 1.1.0) | Indexes `ix_login_attempts_ts`, `ix_sessions_last_seen`, `ix_inbound_events_received` for the retention deletes; forward-only |
| `0040` | Added (2026-11-16) | `throttle_state.is_test`, primary key `(type, is_test)`: test fires are throttled among themselves and never delay a real alert; existing rows are real-fire state |
| `0041` | Added (2026-11-16) | Inbound inputs: the old authentication behaviour made explicit (`auth_required: false` for an input without a token or flag; a non-boolean flag becomes the boolean it meant); data only |
| `0042` | Added (2026-11-16) | `api_keys.allowed_cidrs` (JSON, nullable): per-key source allowlist; NULL = any address |
| `0043` | Added (2026-11-16) | `api_keys.rate_limit_per_min` (INT, nullable): per-key rate limit; NULL = no limit |
| `0044` | Added (2026-11-16) | `api_keys.allowed_types` (JSON, nullable): the alert types (or patterns) a key may fire; NULL = every type |

### Provider lifecycle (`0029`)

`lifecycle_commands` — an action owed to a provider about one delivery
(today `cancel_receipt` for a Pushover emergency): `delivery_id` (FK, cascade),
`provider`, `action`, `ref` (the receipt), `state` (`pending` / `done` /
`failed`), `attempts`, `next_attempt_at`, `last_error`, timestamps. Unique
`(delivery_id, action)` makes a second acknowledgement a no-op; index
`(state, next_attempt_at)` serves the due scan.

`inbound_events` — provider events applied once: unique
`(provider, event_key)` (e.g. `pushover`, `receipt:<r>`), `received_at`,
`result` (`acknowledged` / `expired`). Retention removes rows after 7 days
(by `ix_inbound_events_received`, 0039).

Telegram keeps its own `channel_provider_*` / `channel_events` tables
(`0026`); these generic tables are for providers whose reference is a string
in `deliveries.provider_ref`.

### Runtime guards (`0016`, `0018`)

`dedup_claims` — atomic admission claim per fire context: primary key
`(type VARCHAR(64), is_test, context_hash VARCHAR(16))`, `notification_id
VARCHAR(64)`, `claimed_at` (indexed). A fire claims its slot with an upsert that
only overwrites a stale claim, so two identical concurrent fires cannot both
create a notification. Pruned by retention.

`schedule_occurrences` — fired-occurrence guard for cron schedules: primary key
`(schedule_id, scheduled_at)` (`schedule_id` FK → `schedules.id`, cascade),
optional `notification_id VARCHAR(64)`, `created_at`. Inserted in the same
transaction that advances `next_fire_at`, so an occurrence fires at most once.
Pruned by retention.

### Telegram actions (`0026`)

`deliveries.action_keyboard` stores the optional callback keyboard before sending.
Existing deliveries retain NULL. Six additional tables hold the workflow:

| Table | Role and constraints |
|-------|----------------------|
| `telegram_bot_state` | SHA-256 bot credential identity, next update offset and last received update time. |
| `channel_action_tokens` | Opaque capabilities, delivery FK, action, bot/chat binding, frozen actor policy, expiry and consumption time. |
| `channel_events` | Inbox keyed by bot identity + update ID; result and optional command FK (`SET NULL`). No raw callback payloads. Pruned after seven days. |
| `channel_action_commands` | One accepted action per delivery (unique FK), actor, fixed snooze deadline, state, bounded attempts and retry time. |
| `channel_provider_messages` | Receipt bound to delivery; unique provider + bot + chat + message ID, plus optional read-only UI URL. |
| `channel_provider_commands` | Unique cleanup operation per receipt, state, bounded attempts and retry time. |

Action/provider commands and receipts cascade with their parent delivery. Retention
protects notifications with pending actions, pending cleanup, or cleanup that has
not yet been queued. See [Telegram setup and semantics](TELEGRAM.md).

This doc mirrors what the migrations create. Drift between this doc
and migrations is a bug.

## Indexes / performance budget

The indexes in the DDL above are the working set targeting these
queries:

| Query | Index used |
|-------|-----------|
| Recent log entries (paged) | `idx_log_fired` |
| Filter log by type | `idx_log_type` |
| Unread notifications | `idx_log_unack` |
| Rules by template_type (engine eval) | `idx_rules_template` |
| Snooze lookup at gating time | `idx_snooze_scope_target` |
| API key lookup at auth time | `idx_apikey_prefix` |
| Audit search by actor | `idx_audit_actor` |

Expected row counts at v1:
- `notifications_log` — 10⁴–10⁶ over a year (depends on rule
  noise). Pruned by retention.
- `audit_log` — 10³–10⁵ per year.
- `rules`, `templates`, `channels`, `inputs`, `variables` — 10²
  total, growing slowly.
- `throttle_state`, `rule_state` — 1 row per type / rule.

If `notifications_log` exceeds ~10⁷ rows, partitioning by
`fired_at` (monthly) is the right next step. Out of scope for v1.
