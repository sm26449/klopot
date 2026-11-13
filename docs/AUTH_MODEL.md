# Authentication & authorization model

`alertd` accepts two distinct credential types. The choice depends on
the caller; both can coexist.

| Credential | For | Lifetime | Revocation |
|------------|-----|----------|------------|
| **API key** (`X-API-Key`) | Service-to-service: NR, scripts, third-party apps, server-side renderers | Long-lived (rotated manually) | Immediate via DB flag |
| **JWT** (`Authorization: Bearer …`) | Browser users (current Flask UI session bridge → eventually standalone React UI) | Short-lived access (15 min) + refresh (7d) | Refresh token revoked → new sessions blocked |

---

## Why both

API keys are the right tool for non-human callers (NR posts on a
30-second cron; a backup script fires once). They're stable, simple
to roll, easy to audit per-caller.

JWTs are the right tool for human sessions: short-lived, refreshable,
tied to a logout. They're also the standard the future React UI will
expect.

Forcing API keys on browser users is bad UX: they'd never expire, and
revoking them on logout requires manual action. Forcing JWTs on
service callers is bad ops: every script would need to refresh its
token on a schedule.

So we support both, with the same scope model.

---

## Phasing

To avoid implementing both on day 1:

- **Phase A (S1 → S10): API keys only.**
  - Service-to-service callers: Node-RED, scripts → API key.
  - Browser users: a companion web app logs in via its own session,
    and its backend holds an API key for `alertd`. The browser never
    sees the alertd key directly — the backend proxies the calls. (Trade-off: browser can't talk to alertd
    directly. OK for v1 since the React UI is post-v1.)

- **Phase B (post-v1, when standalone React UI ships): add JWT.**
  - alertd issues short-lived access tokens (15 min) + long-lived
    refresh tokens (7 days) on `POST /v1/auth/login`.
  - Browser stores access in memory, refresh in HttpOnly cookie.
  - Revocation: `POST /v1/auth/logout` invalidates the refresh
    token; access tokens expire on their own within 15 min.

This phasing keeps S1-S10 small and gets the service shipping. The
JWT addition in Phase B is about 200 LOC plus tests.

---

## API key model

### Schema

```sql
CREATE TABLE api_keys (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,        -- "node-red", "web-backend", "backup-script"
    key_hash VARCHAR(255) NOT NULL,           -- bcrypt of the plaintext key
    key_prefix VARCHAR(8) NOT NULL,           -- first 8 chars (for UI display + log audit)
    scopes JSON NOT NULL DEFAULT '["fire"]',  -- array of scope strings
    enabled BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP NULL,                -- optional auto-expiry
    last_used_at TIMESTAMP NULL,
    last_used_ip VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rotated_from_id BIGINT NULL                -- chain rotated keys for audit
);
```

Plaintext keys are 32-byte URL-safe random strings:
`alertd_xX7n4Kv9...` (43 chars after the prefix). The prefix is
displayed in admin lists (`alertd_xX7n4Kv9 ... ****`) so an operator
can identify which key did what without seeing the secret.

### Key issuance flow

```
admin POSTs   /v1/api_keys   { name: "node-red", scopes: ["fire"] }
              ↓
alertd:
  1. Generate 32 random bytes → b64-url encoded
  2. Plaintext = "alertd_" + b64
  3. Hash via bcrypt(cost=12)
  4. Insert row with key_hash + key_prefix
  5. Return 201 { id, name, key: "<plaintext, shown ONCE>", ... }
              ↓
admin saves the plaintext somewhere safe.
Subsequent GETs never expose the plaintext again.
```

### Authentication on each request

Header: `X-API-Key: alertd_xX7n4Kv9...`

Middleware:

1. Extract header (400 if absent and endpoint requires auth)
2. Look up by `key_prefix` (first 8 chars) — fast index hit
3. Bcrypt-verify the full key against `key_hash`
4. Check `enabled = TRUE` and `expires_at IS NULL OR expires_at > NOW()`
5. Update `last_used_at`, `last_used_ip` (best-effort, batched)
6. Attach `request.state.actor = {kind: 'api_key', id, name, scopes}`
7. Endpoint-level decorator checks scope match
8. Audit log entry on admin writes

### Rotation

`POST /v1/api_keys/{id}/rotate` returns a new plaintext key and:

- Marks the old key for revocation in `grace_period_sec` (default 60)
- During grace, both keys work; after grace, old returns 401
- `rotated_from_id` chains forward for audit trail

This lets rolling deploys swap secrets without downtime.

### Scopes

Hierarchical — `admin` implies all others.

| Scope | Allowed endpoints |
|-------|-------------------|
| `fire` | `POST /v1/fire`, `POST /v1/fire/by-rule/{id}` |
| `read` | All `GET` endpoints |
| `ack` | `POST /v1/log/{id}/ack`, `POST /v1/log/{id}/snooze`, `POST /v1/snooze` |
| `admin` | All endpoints (CRUD on inputs/rules/templates/channels/api_keys/settings) |

Multiple scopes per key: `["fire", "read"]` is fine. The middleware
allows the request if any of the key's scopes covers the endpoint.

---

## Browser sessions (admin UI) — implemented 2026-11 (migration 0008)

> Replaces the JWT design that was sketched here. Same-origin SPA served by alertd
> at `/admin/` → an opaque server-side session is simpler and safer:
> **no signing key exists**, so nothing can leak or need rotation, and
> revocation is immediate.

### Model

| Table | Purpose |
|-------|---------|
| `admin_users` | `admin` account (v1: exactly one row). `password_hash` = argon2id PHC string; `must_change_password`; `is_active`. |
| `admin_sessions` | one row per login: `token_hash` = sha256 of the cookie value, `csrf_token`, `created_at`, `last_seen_at`, `expires_at`, `revoked_at`, `ip`, `user_agent`. |
| `login_attempts` | one row per login attempt (`success` flag) — lockout source, pruned after `ALERTD_AUTH_HISTORY_DAYS`. |

Password hashing: **argon2id** (`argon2-cffi` defaults: t=3, m=64 MiB,
p=4). API keys keep bcrypt — they are 256-bit random strings. Policy
(NIST 800-63B): 12–256 characters, must differ from the username and
from the current password; no composition rules, no forced rotation.

### Cookies

| Cookie | Content | Flags |
|--------|---------|-------|
| `alertd_session` | 32 random bytes (`secrets.token_urlsafe`) | `HttpOnly; Secure*; SameSite=Strict; Path=/; Max-Age=SESSION_MAX_DAYS` |
| `alertd_csrf` | 32 random bytes, equal to `admin_sessions.csrf_token` | same, **without** HttpOnly (the SPA reads it) |

`*Secure` follows `ALERTD_COOKIE_SECURE` (default `true`; `false` only
for plain-HTTP development).

Lifetime: `expires_at = min(created_at + ALERTD_SESSION_MAX_DAYS,
last_seen_at + ALERTD_SESSION_IDLE_HOURS)` (defaults 7 d / 12 h),
recomputed on every DB touch. Resolved sessions are cached in-process
for 30 s (same TTL as API keys); the cache is dropped on logout,
revoke and password change so those take effect on the next request.

### Request resolution (`app/auth.py:get_current_actor`)

1. `X-API-Key` header present → API-key path (unchanged).
2. Else `alertd_session` cookie → `admin_sessions` lookup →
   `Actor(kind="user", scopes={"admin"})`.
3. Else 401.

For a cookie-authenticated **write** (anything but GET/HEAD/OPTIONS):

- `Sec-Fetch-Site`, when sent, must be `same-origin` or `none`;
- `Origin`, when sent, must match `Host`;
- `X-CSRF-Token` must equal the session's `csrf_token`
  (double-submit; compared in constant time);
- while `must_change_password` is set, only `POST /v1/auth/password`
  and `POST /v1/auth/logout` are accepted → otherwise
  `403 PASSWORD_CHANGE_REQUIRED`.

API-key callers never see any of this (no cookie → no CSRF). Reads
remain allowed during a forced password change so the UI can render.

### Endpoints (`/v1/auth`)

| Method | Path | Who | Notes |
|--------|------|-----|-------|
| POST | `/login` | public | `{username, password}` → 200 + cookies + `{user, csrf_token}`; `401 INVALID_CREDENTIALS` (same body for unknown user / wrong password / disabled); `423 LOCKED_OUT` + `Retry-After`. |
| POST | `/logout` | session | revokes this session, clears cookies. |
| GET | `/me` | session | user, scopes, current session. |
| POST | `/password` | session | `{current_password, new_password}` → 204; clears `must_change_password`; **revokes every other session**. `400 PASSWORD_POLICY`. |
| GET | `/sessions` | session | own active sessions (`current` flag). |
| DELETE | `/sessions/{id}` | session | revoke one (404 if not own). |
| DELETE | `/sessions` | session | revoke all others → `{revoked}`. |

"session" = `require_user_session`: an API key — even with `admin`
scope — gets `403 SESSION_REQUIRED`. Machines do not manage people's
passwords.

### Lockout (`app/core/login_guard.py`)

Sliding window over `login_attempts`: a username is locked after
`ALERTD_LOGIN_MAX_FAILURES` (5) failures in the last
`ALERTD_LOGIN_LOCKOUT_MIN` (15) minutes *since its last success*; a
source IP after `ALERTD_LOGIN_MAX_FAILURES_PER_IP` (20) failures in the
same window. The lock lifts when the N-th most recent failure ages out
(`retry_after_sec` tells the client when). No separate lock state →
a restart cannot clear it; the CLI can (`unlock`).

Every outcome is audited: `auth.login_ok`, `auth.login_failed`,
`auth.login_blocked`, `auth.logout`, `auth.password_changed`,
`auth.password_change_failed`, `auth.session_revoked`,
`auth.sessions_revoked_others`, plus the CLI actions
(`auth.password_reset_cli`, `auth.unlock_cli`,
`auth.sessions_revoked_cli`). Passwords never appear in the audit rows.

### Bootstrap and break-glass

- First boot: if `admin_users` is empty and
  `ALERTD_ADMIN_BOOTSTRAP_PASSWORD` (≥ 12 chars) is set, the seed
  creates `admin` with `must_change_password=1`. Log in, change the
  password, **remove the variable from `.env`**. Later boots never
  touch the table, even if the variable is still present.
- Lost password / locked out / suspicious session:
  `docker compose exec alertd python -m scripts.admin
  reset-password | unlock | list-sessions | revoke-sessions`.
  `reset-password` prints a temporary password once, forces a change
  and revokes every session. Container shell access is the trust
  boundary; there is deliberately no API for this.

### Not done yet (later phases)

- WebSocket endpoints still authenticate only via `?api_key=`; cookie
  auth for `/v1/stream/*` lands with the UI shell (F2).
- Behind traefik the recorded `ip` is traefik's unless gunicorn is
  told to trust `X-Forwarded-For` (`FORWARDED_ALLOW_IPS`) — F9.

---

## CSRF

API keys: not relevant — no cookies involved.

Browser sessions: `SameSite=Strict` on both cookies, plus the
double-submit `X-CSRF-Token` header and the `Sec-Fetch-Site` /
`Origin` checks described above. All three must pass on every
cookie-authenticated write.

---

## Audit trail

Every admin write writes to `audit_log`:

```
{
  ts: "2026-05-09T20:30:00Z",
  actor_kind: "api_key" | "jwt",
  actor_id: 7,            # api_keys.id or user.id
  actor_name: "admin-cli", # for fast lookup
  action: "rule.update",
  resource_id: 42,
  before: {...},  # JSON of the row pre-change
  after:  {...},  # JSON of the row post-change
  trace_id: "01HV7B2..."
}
```

Retention: configurable, default 365 days (longer than log retention
because audit is rarer and more important).

`GET /v1/audit?actor=...&action=...&from=...&to=...` for admin
review.
