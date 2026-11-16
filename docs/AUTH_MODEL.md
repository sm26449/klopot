# Authentication & authorization model

`alertd` accepts two distinct credential types. The choice depends on
the caller; both can coexist.

| Credential | For | Lifetime | Revocation |
|------------|-----|----------|------------|
| **API key** (`X-API-Key`) | Service-to-service: NR, scripts, third-party apps, server-side renderers | Long-lived (rotated manually) | Immediate via DB flag |
| **Browser session** (`alertd_session` cookie + `X-CSRF-Token`) | The built-in admin UI at `/admin/` (see [Browser sessions](#browser-sessions-admin-ui--implemented-2026-11-migration-0008)) | Idle timeout `ALERTD_SESSION_IDLE_HOURS`, hard cap `ALERTD_SESSION_MAX_DAYS` | Immediate (server-side row revoked) |

---

## Why both

API keys are the right tool for non-human callers (Node-RED posts on a
30-second cron; a backup script fires once). They're stable, simple
to roll, easy to audit per-caller.

Human users of the built-in admin UI get a server-side browser session
instead: it expires when idle, ends on logout, and never puts a long-lived
secret in the browser. Forcing API keys on browser users is bad UX (they'd
never expire, and revoking them on logout requires manual action).

Both share the same scope model. An earlier plan for JWT access / refresh
tokens was dropped in favour of the opaque session (see
[Browser sessions](#browser-sessions-admin-ui--implemented-2026-11-migration-0008));
the `jwt` value of `audit_log.actor_kind` is a leftover of that plan and is
never written.

---

## API key model

### Schema

```sql
CREATE TABLE api_keys (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,        -- "node-red", "web-backend", "backup-script"
    key_hash VARCHAR(255) NOT NULL,           -- bcrypt of the plaintext key
    key_prefix VARCHAR(8) NOT NULL,           -- first 8 chars (for UI display + log audit)
    key_digest VARCHAR(64) NULL UNIQUE,       -- sha256 of a generated key (lookup without bcrypt)
    scopes JSON NOT NULL DEFAULT '["fire"]',  -- array of scope strings
    enabled BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP NULL,                -- optional auto-expiry
    last_used_at TIMESTAMP NULL,
    last_used_ip VARCHAR(45),
    allowed_cidrs JSON NULL,                  -- source allowlist; NULL / [] = any address (0042)
    rate_limit_per_min INT NULL,              -- requests a minute; NULL = no limit (0043)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rotated_from_id BIGINT NULL                -- chain rotated keys for audit
);
```

Plaintext keys are 32-byte URL-safe random strings:
`alertd_xX7n4Kv9...` (43 chars after the prefix). The prefix is
displayed in admin lists (`alertd_xX7n4Kv9 ... ****`) so an operator
can identify which key did what without seeing the secret.

### How a key is verified

1. **Cache** — a key verified in the last 30 seconds is not looked up again.
2. **Digest** — a generated key (`alertd_` + 43 characters, 256 random bits)
   is found by `key_digest`, the SHA-256 of its text: one indexed read, no
   bcrypt. A fast hash is enough for a random secret of that size.
3. **bcrypt** — only for rows without a digest: keys issued before schema
   0034 (the digest is written on their first successful use, so each takes
   this path once) and keys the operator chose in another shape, such as an
   `ALERTD_BOOTSTRAP_ADMIN_KEY` of their own wording. A chosen key may be
   weak, and a fast hash of a weak secret is cheap to reverse from a leaked
   table, so such a key never gets a digest. A bootstrap key in the generated
   shape (what the documented generator prints) is treated as generated; one
   in that shape that is visibly not random (fewer than 16 distinct
   characters) is refused at seed time. Rotate the bootstrap key to a
   generated one after first use.

### Wrong keys are bounded

On the bcrypt path, verifying a key costs a hash (~250 ms of CPU) for every
key without a digest that shares its 8-character prefix, so an
unauthenticated caller must not be able to ask for many:

- **Per address:** 5 wrong keys within 60 s, then `429` + `Retry-After: 60`
  without hashing. The address is the real client behind
  `ALERTD_TRUSTED_PROXY_CIDRS` (HTTP and the WebSocket `?api_key=` alike;
  when every `X-Forwarded-For` hop is trusted, the TCP peer), and an IPv6
  client counts by its /64. Each attempt is counted before it is hashed and
  given back if the key turns out right, so a burst of concurrent wrong keys
  gets 5 hashes, not one each. A key already in the cache is not affected;
  one that has to be verified again from that address waits out the minute.
- **Queue:** at most `ALERTD_HASH_MAX_CONCURRENCY` verifications run and 16
  wait; beyond that the answer is `503` + `Retry-After: 1`.
- **No database connection** is held while a key is hashed.

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

1. Extract header (401 if absent and the endpoint requires auth)
2. Look up by `key_prefix` (first 8 chars) — fast index hit
3. Bcrypt-verify the full key against `key_hash`
4. Check `enabled = TRUE` and `expires_at IS NULL OR expires_at > NOW()`
5. Update `last_used_at`, `last_used_ip` (best-effort, batched)
6. Attach `request.state.actor = {kind: 'api_key', id, name, scopes}`
7. Endpoint-level decorator checks scope match
8. Audit log entry on admin writes

### Source allowlist

A key may be limited to the addresses it is used from: `allowed_cidrs`, a
list of IPs or CIDRs, IPv4 and IPv6 (at most 64; empty = any address, which
every key has unless you set one). Set it in the admin UI (API keys → the
key → Allowed addresses; "Add my address" fills in yours as Klopot sees it)
or with `allowed_cidrs` on `POST` / `PATCH /v1/api_keys`. Entries are
stored normalised (`10.0.0.7/24` → `10.0.0.0/24`); a `/0` is refused,
because an empty list already means "any".

- **Checked on every request** with the key — HTTP and the WebSocket
  `?api_key=` alike, a cached key too — after the key is known to be right
  and before its use is recorded, against the real client address (behind
  `ALERTD_TRUSTED_PROXY_CIDRS`, as above; an IPv4-mapped IPv6 address
  matches its IPv4 network).
- **From elsewhere: `403`** ("This API key is not allowed from this
  address"), counted **once** as a wrong key for that address — so a leaked
  key used from outside its networks also runs into the `429` above.
  `last_used_at` / `last_used_ip` are not updated by a refused request.
- **Changes apply at once:** editing the list drops the key's cached
  credentials and closes its live streams, which must reconnect from an
  allowed address. Rotation copies the list to the new key.

Give every key used from outside your network both a `fire`-only scope and
the narrowest list you can.

### Rate limit

A key may be limited to a number of requests a minute: `rate_limit_per_min`
(1–60000; empty = no limit, which every key has unless you set one). Set it
in the admin UI (API keys → the key → Requests per minute) or on `POST` /
`PATCH /v1/api_keys` (`null` removes it).

- **How it counts** (GCRA, `app/utils/rate_limit.py`): a key that has been
  quiet may send N requests at once, then one every 60/N seconds — the
  steady rate is N a minute, without a cliff at a minute boundary.
- **Over it: `429`** ("This API key is limited to N requests a minute") with
  `Retry-After`, the whole seconds until the next request fits. A refused
  request spends nothing, so a client that waits `Retry-After` gets in.
- **Every request with the key counts**, HTTP and the WebSocket handshake,
  cached or not — and only requests with the right key: it is not a wrong
  key, and does not touch any address's wrong-key budget. Order: key, then
  source allowlist, then rate limit.
- **Per key, not per address**: a key used from several places shares one
  allowance. Per-address limits for the public `/v1/fire` belong in the
  proxy ([DEPLOY](DEPLOY.md), `compose.public.yml`).
- **Kept in the process** (Klopot runs one worker): a restart refills every
  key. Editing the key, or its cached credentials expiring, does not; a
  lower limit applies to what is already spent (10 requests at 60/min are
  10 s of the minute — at 6/min, room for 5 more). Rotation copies the limit;
  during a rotation grace period the old and the new key count separately.
- **Watch it**: `alertd_api_key_rate_limited_total{key}` on `/metrics`, and
  the refused requests (status 429) in the Activity log.

Size the limit from the caller's normal rate with room for bursts: a
script that fires once a minute needs about 5, a UI that polls every few
seconds 60 or more.

### Rotation

`POST /v1/api_keys/{id}/rotate` returns a new plaintext key and:

- With `?grace_sec=N` (0–600, default 0 = revoke immediately) the old key
  stays valid for N seconds
- During grace, both keys work; after grace, old returns 401
- `rotated_from_id` chains forward for audit trail
- The new key keeps the old key's scopes, expiry, source allowlist and rate limit

This lets rolling deploys swap secrets without downtime.

### Scopes

Hierarchical — `admin` implies all others.

| Scope | Allowed endpoints |
|-------|-------------------|
| `fire` | `POST /v1/fire` — a fire with `test: true` is marked as a test but gated, throttled and de-duplicated like a real alert |
| `read` | `GET` endpoints, except the admin-only reads below; also the side-effect-free `POST /v1/rules/validate`, `POST /v1/rules/{id}/eval-now`, `POST /v1/templates/{type}/preview`, `POST /v1/activity/rules/preview`, and `POST /v1/push/subscriptions` (signed-in session only) |
| `ack` | `POST /v1/log/{id}/ack`, `POST /v1/incidents/{id}/ack`, `POST /v1/incidents/{id}/resolve`, `POST /v1/snooze`, `DELETE /v1/snooze/{id}` |
| `admin` | All endpoints: every create/update/delete, channel/rule/schedule tests (and its `test: true` fires skip throttle, the delivery gate, quiet hours and de-duplication), config export/import, packs inspect/preview/apply, setup dismiss/reopen, plus the reads `GET /v1/api_keys`, `GET /v1/config/export` and `GET /v1/activity/requests/{id}` |

Public (no scope): `/v1/health`, `/v1/health/ready`, `/v1/version`,
`POST /v1/auth/login`, `POST /v1/inputs/{id}/webhook` (per-input
`X-Input-Token`) and `/v1/metrics` unless `ALERTD_METRICS_REQUIRE_AUTH`
(default: on when `ALERTD_COOKIE_SECURE` is true) requires a `read` key. `/v1/auth/*` besides login
needs a browser session. Each operation's scope is in `/openapi.json` as
`x-required-scope`.

**Inbound inputs** (`POST /v1/inputs/{id}/webhook` — webhook, sms_inbox,
alertmanager) require their token unless the input's config says
`auth_required: false` (the boolean; any other value fails closed). An input
that requires a token without having one is refused when it is saved (REST
or import). The endpoint says nothing about an input before its token is
accepted: an id that is no live inbound input (missing, another kind,
disabled) and a wrong or missing token all get the same `401`. Each of those
counts against the sending address — five a minute, then `429` for every
request from it, the right token included, so guessing stops there. This
budget is separate from the API keys': a sender with a stale token does not
lock out the keys used from the same address.

A token needs at least **32 characters** (`openssl rand -base64 32`), judged
whenever the authentication is set or changed — on create, an edit of
`auth_token` / `auth_token_ref` / `auth_required`, or an import that brings
a different one; for `auth_token_ref`, the variable's value is measured
(one not set yet cannot be, and the input refuses every post until it is).
An input saved before this floor keeps working and stays editable;
`GET /v1/inputs` says `token_too_short: true` and the Inputs page marks it.

Turning authentication off is for a sender on your own
network that cannot send a header; the public traefik overlay never opens
this endpoint (docs/DEPLOY.md).

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
  boundary; there is deliberately no API for this. The CLI runs in its
  own process and cannot drop the server's 30-second session cache: a
  session revoked from it keeps working for up to 30 s (an open live
  stream is re-checked on the same 30-second cycle). Revoking from the
  admin UI or the API takes effect on the next request.

### Client address behind a proxy

Login throttling, the wrong-key budget, `api_keys.last_used_ip` and the
activity log use the real client address: when the TCP peer is inside
`ALERTD_TRUSTED_PROXY_CIDRS`, the rightmost `X-Forwarded-For` entry that is
not itself a trusted proxy. Without that setting the address is the proxy's
and every client shares one budget.

The WebSocket streams (`/v1/stream/*`) accept the session cookie (same-origin
only) or an API key.

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
  actor_kind: "api_key" | "user" | "system",   # user = browser session
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
