# Schema reference

Authoritative DDL for the alertd MySQL schema. Updated alongside
Alembic migrations. The DDL below is conceptual (MySQL 8.0
dialect); the actual column types and indexes live in
`app/db/models.py` and the Alembic versions (all shipped — see the
Migrations table at the end).

## Conventions

- All `id` columns are `BIGINT AUTO_INCREMENT PRIMARY KEY` unless
  otherwise noted.
- All timestamps are `TIMESTAMP` with implicit `CURRENT_TIMESTAMP`
  defaults; UTC stored, local rendered.
- All JSON columns are `JSON` type (MySQL 8.0 native, validated
  on insert).
- Foreign keys use `ON DELETE` semantics documented per table.
- All "lifecycle" columns (`enabled`, `created_at`, `updated_at`)
  are present unless the table is purely runtime state (e.g.,
  `rule_state`).
- Names: snake_case, plural for entity tables, singular for state
  tables.

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
              'sms_inbox','email_imap') NOT NULL,
    config JSON NOT NULL,
        -- Per-kind shape (validated at write time by Pydantic):
        -- mqtt: {host, port, username, password_ref, client_id, qos}
        -- http_poll: {url, method, headers, interval_sec, json_path, timeout_sec}
        -- webhook: {auth_required, allowed_ips}
        -- schedule: {cron}
        -- sms_inbox: {gateway_url, auth_token_ref}
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
    name VARCHAR(128) NOT NULL UNIQUE,    -- e.g., "battery.soc"
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
    icon VARCHAR(8),
    title_template TEXT NOT NULL,
    message_template TEXT,
    runbook_url VARCHAR(500),
    description TEXT,
    locale VARCHAR(8) NOT NULL DEFAULT 'en',
    -- Behavior tuning at template scope (rule overrides where applicable)
    min_repeat_min INT NOT NULL DEFAULT 30,    -- cooldown
    require_pv_kw FLOAT,                       -- daylight gate (optional)
    quiet_hours JSON,                          -- {"sms":"22-07", ...}
    category VARCHAR(64),                      -- UI grouping (migration 0003)
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tmpl_severity (severity),
    INDEX idx_tmpl_enabled (enabled)
);
```

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
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_rules_template (template_type),
    INDEX idx_rules_enabled (enabled, sort_order)
);
```

### `rule_state`

Runtime state per rule (fast counter, separate from config so admin
edits don't lose ramp-up progress).

```sql
CREATE TABLE rule_state (
    rule_id BIGINT PRIMARY KEY,
    consecutive_match_count INT NOT NULL DEFAULT 0,
    last_match_at TIMESTAMP,
    last_eval_result JSON,             -- last evaluated context for debugging
    FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE CASCADE
);
```

### `channels`

Output destination declarations.

```sql
CREATE TABLE channels (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    kind ENUM('ui','banner','telegram','sms','email','push','webhook') NOT NULL,
    config JSON NOT NULL,
        -- Per-kind shape (secrets via _ref):
        -- ui: {} (broadcasts via WebSocket; no config)
        -- banner: {} (in-app banner; no config)
        -- telegram: {bot_token_ref, chat_id, parse_mode}
        -- sms: {gateway_url, phone, gateway_api_key_ref}
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

### `notifications_log`

Canonical history of every fire (dispatched + suppressed).

```sql
CREATE TABLE notifications_log (
    id VARCHAR(64) PRIMARY KEY,         -- "ntf_<unix_ms>_<type>"
    template_id BIGINT,                  -- nullable: unknown_type fires
    rule_id BIGINT,                      -- nullable: external /v1/fire
    type VARCHAR(64) NOT NULL,
    severity ENUM('info','warning','critical') NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT,
    vars_payload JSON,
    -- Dispatch
    fired_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dispatched_to JSON NOT NULL DEFAULT '[]',
    failed_channels JSON NOT NULL DEFAULT '{}',
    suppressed_reason ENUM(
        'disabled','snoozed','throttled','persist','gated',
        'duplicate','unknown_type'
    ),
    dispatch_latency_ms INT,
    -- User actions
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(64),
    snoozed_until TIMESTAMP,
    -- Audit / observability
    source VARCHAR(64),                  -- "node-red", "internal-engine", caller name
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

### `throttle_state`

Last-fire tracker per type — single row per template type.

```sql
CREATE TABLE throttle_state (
    type VARCHAR(64) PRIMARY KEY,
    last_fired_at TIMESTAMP,
    persist_count INT NOT NULL DEFAULT 0,
    persist_last_seen TIMESTAMP
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
    scopes JSON NOT NULL DEFAULT '["fire"]',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMP NULL,
    last_used_at TIMESTAMP NULL,
    last_used_ip VARCHAR(45),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rotated_from_id BIGINT NULL,
    INDEX idx_apikey_prefix (key_prefix),
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
    actor_kind ENUM('api_key','jwt','system') NOT NULL,
    actor_id BIGINT,                        -- api_keys.id or user.id
    actor_name VARCHAR(64),
    action VARCHAR(64) NOT NULL,
        -- "rule.create", "rule.update", "rule.delete", "channel.create", ...
    resource_kind VARCHAR(32),
    resource_id VARCHAR(64),
    before JSON,
    after JSON,
    trace_id VARCHAR(40),
    INDEX idx_audit_ts (ts DESC),
    INDEX idx_audit_actor (actor_id, ts DESC),
    INDEX idx_audit_action (action, ts DESC),
    INDEX idx_audit_resource (resource_kind, resource_id)
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
    bridge_max_queue INT NOT NULL DEFAULT 100,    -- replaces NR queue
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
    INDEX ix_sessions_user_active (user_id, revoked_at, expires_at)
);

CREATE TABLE login_attempts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts DATETIME NOT NULL,
    username VARCHAR(64) NULL,
    ip VARCHAR(45) NULL,
    success BOOLEAN NOT NULL,
    INDEX ix_attempts_user_ts (username, ts),
    INDEX ix_attempts_ip_ts (ip, ts)
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
