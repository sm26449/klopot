# Non-functional requirements & limits

Explicit targets for v1.0. If a deployment exceeds these, we either
re-tune or escalate to a horizontally-scaled architecture (see
`DEPLOY.md` Concurrency model section).

## Throughput

| Metric | Target (v1.0) | Reasoning |
|--------|---------------|-----------|
| Inbound MQTT messages | 1000 msgs/min | A typical home/site telemetry load peaks at ~500-800 msgs/min; 2× headroom |
| Rules evaluated per second | 50/s | 100 rules × default 10s eval interval = 10 evals/s avg, 50/s under burst |
| `/v1/fire` POSTs | 100/min | Node-RED + scripts combined |
| Notifications dispatched | 60/min | After throttle/persist; per-channel rate-limited at 30/min default |
| WebSocket clients connected | 20 simultaneous | Operator browsers + UI tabs + future mobile |

## Latency

| Path | p50 | p95 | p99 |
|------|-----|-----|-----|
| `POST /v1/fire` round-trip (idempotency-only path) | 5 ms | 30 ms | 80 ms |
| `POST /v1/fire` with full dispatch (UI channel only) | 10 ms | 50 ms | 150 ms |
| `POST /v1/fire` with Telegram + SMS dispatch | upstream | upstream | ≤ 45 s (waits for the first attempt) |
| Rule evaluation (one rule, one tick) | 1 ms | 5 ms | 30 ms |
| `GET /v1/log?limit=50` | 20 ms | 100 ms | 500 ms |
| MQTT msg → state cache update | 1 ms | 5 ms | 20 ms |
| MQTT msg → rule fire (worst-case persist=1) | 1 sec | 11 sec | 31 sec |
  (next tick boundary, max 1×eval_interval) | | | |

p99 dispatch latencies for Telegram/SMS/email depend on upstream;
budgets are alertd-internal only. `dispatch_latency_ms` in the log
includes upstream wait.

Dispatch is not asynchronous: the first attempt is sent inline, to all
channels in parallel, bounded by `FIRST_ATTEMPT_BUDGET_SEC` (45 s,
`app/core/outbox.py`); what does not finish in time is left to the delivery
worker. `POST /v1/fire` returns only after that attempt. Incident notices
(`background_only`) skip it, but a plain rule fire runs it inside the rule
engine's loop, so a slow channel delays every other rule for that long.
After 180 s without a turn, health reports engine `degraded`
(`engine_stalled`); readiness deliberately stays `200` (see
`ARCHITECTURE.md`, Delivery path).

## Storage

| Table | Expected at 1 year | Pruning |
|-------|---------------------|---------|
| `notifications_log` | 1-10 M rows (depends on noise) | Daily retention, default 90d |
| `audit_log` | 0.1-1 M rows | Daily retention, default 365d |
| All config tables (rules/templates/...) | <1000 rows | Manual; small |

DB disk projection at 1 year: **~5-50 GB**. Plan for 100 GB
volume to absorb spikes and seasonal noise.

If `notifications_log` rows exceed 10⁷, we partition by month
(MySQL native partitioning). Out of scope for v1.

## Memory

| Component | Resident set |
|-----------|--------------|
| FastAPI + Python runtime | 80 MB |
| State cache (~50 vars × ~1KB) | 50 KB |
| Active rule evaluator state | 200 KB (counters + last_match) |
| WebSocket clients buffer | 10 MB max (20 clients × 500KB queue) |
| MySQL pool | 30 MB (10 connections idle) |
| **Total at idle** | **~150 MB** |
| **Total under load (1000 msgs/min)** | **~250 MB** |

Container memory limit: 512 MB recommended (3× headroom).

## CPU

At target throughput (1000 msgs/min, 100 rules at 10s):
- MQTT receive/filter/cache: <2% of one core
- Rule evaluation: <1% of one core
- DB I/O: <2% of one core
- HTTP API: <1% of one core (bursts higher on `/v1/log` queries)

Container CPU limit: 1.0 (full core, 5× headroom).

## Network

- Internal (MySQL, MQTT): <1 Mbit/s sustained
- External (Telegram/SMS/email APIs): <100 KB/s sustained
- WebSocket fan-out: <1 KB/s per client × 20 = <20 KB/s

## Restart / recovery

| Operation | Target time |
|-----------|-------------|
| Container start to healthy | <15 s |
| MQTT subscriptions re-established after reconnect | <5 s |
| State cache refilled from MQTT retained messages | <2 s |
| Migration `alembic upgrade head` (additive) | <30 s |
| Restore from MySQL dump (1 GB) | <5 min |
| Full container rebuild | <2 min (no cache) |

Health probe wait: 20 s start_period in Dockerfile, 30 s interval.

## Reliability

- **Availability target:** 99.5% over rolling 30 days (≤ 3.6 h
  downtime per month). Single-tenant home deployment; no SLA.
- **Data durability:** every fire is persisted to
  `notifications_log`, together with one `deliveries` row per channel,
  BEFORE channel dispatch. Delivery is at-least-once: a crash can
  duplicate a send (the delivery worker retries unfinished rows after
  restart) but never loses one. Idempotency ensures retries don't
  duplicate the log row.
- **Backup recovery point:** ≤ 24 h (daily MySQL dump).
- **Backup recovery time:** ≤ 30 min (restore + replay events from
  retained MQTT).

## Security

- Secrets: a `*_ref` field (an environment variable name, e.g.
  `KLOPOT_SECRET_*`) keeps the secret out of the database and git. A secret
  typed into the admin UI or API as a literal value **is** stored in the
  database, and so in its backups; use refs in production (`DEPLOY.md`,
  Secrets).
- TLS via reverse proxy (traefik overlay, Caddy, nginx); alertd serves
  plain HTTP internally.
- API keys: bcrypt hashed (cost=12); a generated key is also found by an
  indexed SHA-256 digest, so verifying it needs no bcrypt (AUTH_MODEL.md).
  Admin passwords: argon2id.
- Rate limiting: an API key or an inbound input may have its own request
  limit (`rate_limit_per_min`). Wrong API keys and refused input tokens are
  bounded per client address (5 a minute each, then `429`). Logins are
  throttled per (username, address), per username and per address
  (`ALERTD_LOGIN_MAX_FAILURES*`, IPv6 by /64); outbound sends
  are rate-limited per channel (`rate_limit_per_min`); request bodies are
  capped (`ALERTD_MAX_REQUEST_BYTES`).
- Audit retention 365 days minimum.
- No PII intentionally stored. Log rows can include user-supplied
  context (e.g., phone numbers in SMS-inbound) — operator's
  responsibility to scrub if required.

## Limits we won't exceed in v1

These are intentional caps. Removing them is a v2 conversation.

- 100 rules total (eval cost grows linearly) — enforced at create
- 50 inputs total — enforced at create
- 20 channels total — enforced at create
- 1 worker / 1 process / 1 host (no clustering)
- Single MySQL instance (no replication)
- 90 day default log retention
- 5 min idempotency window
- 10 s default eval interval (can be lowered per rule to 1 s minimum)

The entity caps are enforced at create — both the REST `POST` handlers and
config import return **409 `LIMIT_REACHED`** once a capped entity is at its
limit. They are configurable via `ALERTD_MAX_RULES`, `ALERTD_MAX_INPUTS` and
`ALERTD_MAX_CHANNELS` (default 100/50/20; `0` disables a cap). Only genuinely
new rows are gated, so an instance already over a (lowered) cap keeps running
and can re-import its own config. **An instance already above a cap must raise
the matching `ALERTD_MAX_*` before it can create more of that entity.**

## When v1 limits are hit

Trigger for design conversation:

| Indicator | Symptom | Next step |
|-----------|---------|-----------|
| Eval p99 > 100 ms | rule evaluator log warnings | profile slow rules; consider per-input event-driven eval (vs interval-based) |
| Memory > 400 MB | container near limit | inspect cache; check for leaked WebSocket buffers |
| `/v1/fire` p99 > 200 ms | callers timing out | check DB pool saturation, channel circuit breakers |
| Log table > 10 M rows | retention not pruning | tune `log_retention_days`; consider monthly partitioning |
| MQTT lag > 5 s | downstream rules behind | check broker, network, or replicas at message-rate scale |
| Channel error rate > 5% | upstreams flaky | tune circuit breaker, add retry budget, escalate to upstream owners |
