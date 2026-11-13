# Deployment & operations

## Concurrency model — single worker, no leader election

**alertd runs as a single Python process per deployment.** The
`AlertEngine` (MQTT subscriber, rule evaluator, dispatcher) is one
asyncio task in that process. Adding workers / replicas is not
supported in v1.

### Why single-worker

Multiple processes evaluating the same rules independently would:

1. **Duplicate fires.** Both workers see the condition match, both
   write to `notifications_log`, both dispatch to channels. The
   user gets two Telegram messages for one event.
2. **Race the persist counter.** Per-rule `consecutive_match_count`
   would be incremented twice per real tick.
3. **Race the throttle.** Both workers might see "no recent fire"
   in the gap before either records its fire.

Solutions exist (leader election via DB lock, distributed cache,
sharded rule sets), but they add complexity disproportionate to v1
goals. The service handles ~37 declared inputs at <1000 msgs/min;
one Python process is plenty.

### How we enforce it

In `Dockerfile`:
```
gunicorn ... --workers 1 ...
```

In `docker-compose.yml`:
```yaml
alertd:
  # NOT: replicas: 2
  # NOT: deploy.mode: replicated
```

If a deployment ever needs HA, the right path is:

1. **Active/passive with leader election.** Two replicas, only the
   leader runs the engine. DB-based lease (heartbeat to a
   `cluster_lease` table) determines the leader.
2. **Sharded rules.** Each replica owns a subset of rules
   (consistent hash on `rule.id`). Reduces blast radius of one
   replica failing.
3. **Read replicas for queries.** UI / audit queries hit a read-only
   MySQL replica; writes still go to the primary. Engine stays
   single-writer.

None of this is in v1. Documented here so a future contributor sees
the trade-offs.

## docker-compose deployment

### Compose variants

| File | Role |
|------|------|
| `docker-compose.yml` | **Production base**: `alertd` + MySQL 8 + backup sidecar. Host port bound to `127.0.0.1:${KLOPOT_HTTP_PORT:-5090}`; MySQL is never published. |
| `compose.traefik.yml` | **Overlay** — joins an existing traefik's Docker network (`TRAEFIK_NETWORK`, alias `klopot`), adds docker-provider labels for `KLOPOT_HOSTNAME` with TLS + HSTS, forces `ALERTD_COOKIE_SECURE=true`. |
| `compose.dev.yml` | **Overlay** — builds from the checkout (`klopot:dev`), bundles an anonymous Mosquitto on `127.0.0.1:1883`, DEBUG logs, insecure cookies, `/docs` + `/v1/metrics` open, no backup sidecar (`--profile backup` to add it). |
| `compose.demo.yml` | **Standalone** two-minute demo (MySQL on tmpfs, publisher, webhook sink). |

```bash
docker compose up -d                                                 # production
docker compose -f docker-compose.yml -f compose.traefik.yml up -d    # production behind traefik
docker compose -f docker-compose.yml -f compose.dev.yml up --build   # development
```

Set `COMPOSE_FILE` in `.env` (e.g. `COMPOSE_FILE=docker-compose.yml:compose.traefik.yml`)
so plain `docker compose …` commands — and `scripts/deploy.sh` /
`scripts/bootstrap.sh` — always address the right variant.

### Fresh install

```bash
git clone https://github.com/sm26449/klopot.git
cd klopot
cp .env.example .env && $EDITOR .env
# at minimum: MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD (+ the URL),
# ALERTD_MQTT_HOST, ALERTD_ADMIN_BOOTSTRAP_PASSWORD, channel secrets
bash scripts/bootstrap.sh          # or: docker compose up -d
```

`scripts/bootstrap.sh` checks the prerequisites (and, for the traefik
variant, that `TRAEFIK_NETWORK` exists), runs `docker compose up -d
--build`, and waits for `/v1/health`. It is idempotent.

State after the first start:
- `alertd` auto-applies Alembic migrations at startup (fail-fast: a failed
  upgrade aborts startup and the container restart-loops visibly rather
  than running on a stale schema).
- `mysql` creates the `alertd` database if absent.
- Only the bootstrap rows exist: `ui_default` + `banner_default` channels,
  default settings, the `admin` login (if `ALERTD_ADMIN_BOOTSTRAP_PASSWORD`
  is set) and the admin API key (if `ALERTD_BOOTSTRAP_ADMIN_KEY` is set).
  Rules, templates and channels are yours to create — in the admin UI, over
  the API, or by importing a pack from [`examples/`](../examples/)
  (`POST /v1/config/import`).

### Environment variables

See `.env.example`. The full list:

| Var | Default | Purpose |
|-----|---------|---------|
| `COMPOSE_FILE` | `docker-compose.yml` | Compose variant(s), colon-separated |
| `KLOPOT_PROJECT_NAME` | `klopot` | Compose project name (prefixes containers, volumes, networks) |
| `KLOPOT_IMAGE` | `ghcr.io/sm26449/klopot:latest` | Image pulled / tagged by compose |
| `KLOPOT_HTTP_PORT` | `5090` | Host port (bound to `127.0.0.1`) |
| `KLOPOT_HOSTNAME` | — | traefik variant: public hostname |
| `TRAEFIK_NETWORK` | — | traefik variant: external Docker network traefik runs on |
| `TRAEFIK_ENTRYPOINT` | `websecure` | traefik variant: entrypoint name |
| `TRAEFIK_CERTRESOLVER` | `letsencrypt` | traefik variant: certificate resolver name |
| `ALERTD_DATABASE_URL` | `mysql+aiomysql://alertd:alertd@mysql:3306/alertd` | Async SQLAlchemy URL |
| `ALERTD_MQTT_HOST` | `host.docker.internal` in compose, `localhost` in code | Broker hostname |
| `ALERTD_MQTT_PORT` | `1883` | |
| `ALERTD_MQTT_USERNAME` | (empty) | Optional |
| `ALERTD_MQTT_PASSWORD` | (empty) | Optional |
| `ALERTD_MQTT_CLIENT_ID` | `alertd` | Visible in broker connection list |
| `ALERTD_LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `ALERTD_LOG_FORMAT` | `console` | `console` / `json` |
| `ALERTD_TZ` | `UTC` | Timezone for hour_now()/in_window() |
| `ALERTD_PV_POWER_VAR` | (empty) | State-cache variable (kW) that `template.require_pv_kw` gates on. Empty disables the gate. |
| `ALERTD_HASH_MAX_CONCURRENCY` | `4` | Max concurrent password/API-key hashing ops offloaded to threads (bounds CPU + argon2 memory on an auth burst). |
| `ALERTD_MAX_AGGREGATE_MEMBERS` | `1000` | Per-aggregate member budget (audit D1-01). Expired members are evicted; at the budget a new member is refused and the aggregate output invalidated (surfaced by the `alertd_aggregate_overflow` metric), never silently trimmed. `0` = unbounded. |
| `ALERTD_MQTT_QUEUE_MAX` | `10000` | Finite MQTT incoming-queue capacity (audit D1-02). The adapter subscribes to the configured filters, not `#`. On overflow aiomqtt drops (QoS0); a missed update degrades to staleness and a reconnect redelivers retained state. |
| `ALERTD_MQTT_MAX_PAYLOAD_BYTES` | `262144` | Drop (and count, in input health `dropped_oversized`) an MQTT payload larger than this before decode. |
| `ALERTD_MAX_REQUEST_BYTES` | `1048576` | Global inbound request-body cap (audit A-08). An ASGI middleware refuses a larger body with `413` before any handler buffers it. |
| `ALERTD_MAX_WEBHOOK_BYTES` | `65536` | Tighter cap for the public token-gated webhook-ingress endpoint; outsized bodies are rejected before parsing. |
| `ALERTD_MAX_RESPONSE_BYTES` | `4194304` | Decompressed byte cap on an upstream HTTP-poll / webhook response, so a huge or compression-bomb body can't exhaust memory. |
| `ALERTD_MAX_CONFIG_DEPTH` | `50` | Max YAML/JSON nesting depth for config import. Aliases/anchors are rejected outright (billion-laughs). |
| `ALERTD_BOOTSTRAP_ADMIN_KEY` | (empty) | One-time admin API key seeded on first run |
| `TELEGRAM_BOT_TOKEN` | (empty) | Telegram channel secret (resolved via `*_ref` in channel config) |
| `SMTP_PASSWORD` | (empty) | Email channel secret (via `*_ref`) |
| `SMS_GATEWAY_API_KEY` | (empty) | SMS gateway secret (via `*_ref`) |
| `BACKUP_KEEP_DAYS` | `30` | Backup sidecar rotation |
| `BACKUP_CRON` | `0 2 * * *` | Backup sidecar schedule |
| `MYSQL_ROOT_PASSWORD` | — (required) | DB container only |
| `MYSQL_INNODB_BUFFER_POOL_SIZE` | `256M` | DB container only |
| `MYSQL_DATABASE` | `alertd` | DB container only |
| `MYSQL_USER` | `alertd` | DB container only |
| `MYSQL_PASSWORD` | `alertd` | DB container only |

Tuning knobs (`ALERTD_DATABASE_POOL_SIZE`, retention windows,
circuit-breaker thresholds, `ALERTD_CORS_ORIGINS`, …) are listed
with their defaults in `.env.example` and documented in
`app/config.py`.

### Network model

```
                 host 127.0.0.1:5090          traefik (optional overlay)
                         │                            │ TRAEFIK_NETWORK
                         ▼                            ▼ (external, alias "klopot")
                  ┌──────────────┐◄───────────────────┘
                  │    alertd    │──► MQTT broker (host.docker.internal,
                  └──────┬───────┘     or a container on TRAEFIK_NETWORK)
              internal   │
                 ┌───────┴────────┐
                 ▼                ▼
          ┌────────────┐   ┌────────────┐
          │   mysql    │   │   backup   │
          │ (no host   │   │  sidecar   │
          │  port)     │   │            │
          └────────────┘   └────────────┘
```

- Port 5090 is published on `127.0.0.1` only. Anything beyond the host goes
  through a TLS reverse proxy (see "Reverse proxy").
- MySQL is reachable only on the project's private `internal` network.
- MQTT: a broker on the Docker host is reached as `host.docker.internal`
  (mapped via `extra_hosts`). A broker that is a container on the same
  Docker network as traefik is reached by its container name once the
  traefik overlay is in use.

### Healthcheck behavior

The container's healthcheck probes `/v1/health` every 30s; container
is marked unhealthy if 3 consecutive probes fail.

`/v1/health` always returns HTTP 200 (so a degraded-but-running
service is not restarted by Docker). Clients (Prometheus blackbox
exporter, uptime monitors, reverse proxy) inspect the body to
distinguish `ok` / `degraded` / `down`.

## Migrations

Migrations run **automatically at container startup** (`app/main.py`
lifespan runs `alembic upgrade head` before anything else) and are
**fail-fast**: if the upgrade raises, startup aborts and Docker's
restart policy turns it into a visible restart loop — the service
never runs on a half-migrated schema. On failure: check
`docker compose logs alertd`, fix or restore, and restart.

Manual operations:

```bash
docker compose exec alertd alembic current    # inspect revision
docker compose exec alertd alembic history    # list migrations
docker compose exec alertd alembic upgrade head   # manual apply (idempotent)
```

### Upgrading a *populated* legacy database — historical UTC (audit B-09)

A **fresh install needs nothing here.** But if you upgrade a database that
already held data — or move one to a host in a different timezone — some
historical timestamps (`audit_log.ts`, `notifications_log.fired_at` from
migrations 0004/0005, and config-row `created_at`/`updated_at` from the
pre-session-UTC build) can be off by a DST offset. The single-offset backfill in
0004/0005 is **not** universally safe on a populated database. After upgrading,
run the read-only preflight and the repair tools it points to:

```bash
docker compose exec alertd python -m scripts.check_legacy_utc \
    --config-cutoff <SESSION-UTC-DEPLOY-INSTANT>   # read-only; exits 2 if repair needed
```

Full policy and repair procedure: **[`LEGACY_UTC.md`](LEGACY_UTC.md)**.

### Rollback — forward-only (audit V20)

Migrations are **forward-only**. `alembic downgrade` is **refused up front** by a
global preflight (`app/db/migration_guard.py`), before any step runs, so a
command that would tear the schema down cannot start — MySQL DDL is not
transactional, so a downgrade that fails (or whose later step guards itself) can
otherwise leave tables already dropped and committed.

**To roll back a bad deploy, restore the pre-deploy database backup** (below) and
redeploy the previous image — do not downgrade. Forcing a downgrade is possible
with `ALERTD_ALLOW_DOWNGRADE=1`, but it is **not** guaranteed non-destructive and
is intended only for a throwaway/dev database:

```bash
# destructive, dev only — accept possible data loss:
docker compose exec -e ALERTD_ALLOW_DOWNGRADE=1 alertd alembic downgrade -1
```

## Backups

Bundled `backup` sidecar container (see
`docker-compose.yml`). Built from `Dockerfile.backup`, base
`mysql:8.0` so caching_sha2_password works natively. Schedules
backups via a tiny in-image shell loop matching `BACKUP_CRON`
(default `0 2 * * *` — daily at 02:00 server-TZ).

Files land in `./backups/alertd-<UTC-ISO>.sql.gz` on the host. The
sidecar runs an immediate first backup at startup so operators can
verify the pipeline without waiting for the cron tick. Rotation
deletes anything older than `BACKUP_KEEP_DAYS` (default 30).

```yaml
backup:
  build: { dockerfile: Dockerfile.backup }
  environment:
    MYSQL_HOST: mysql
    MYSQL_USER: alertd
    MYSQL_PASSWORD: alertd
    MYSQL_DATABASE: alertd
    BACKUP_KEEP_DAYS: 30
    BACKUP_CRON: "0 2 * * *"
  volumes:
    - ./backups:/backups
```

Restore (single dump file → fresh DB):

```bash
# 1. Stop alertd so no writes interfere
docker compose stop alertd

# 2. Wipe and recreate the DB
docker compose exec -T mysql \
    mysql -u alertd -palertd \
    -e "DROP DATABASE alertd; CREATE DATABASE alertd CHARACTER SET utf8mb4;"

# 3. Restore
zcat backups/alertd-20260510T020000Z.sql.gz | \
    docker compose exec -T mysql mysql -u alertd -palertd

# 4. Bring alertd back
docker compose start alertd
```

The dump uses `--single-transaction` for a consistent snapshot
without locking writes; `--no-tablespaces` skips the global tablespace
metadata (which the alertd user has no PROCESS privilege to read).

## Reverse proxy

Klopot binds its HTTP port to `127.0.0.1`; put a TLS-terminating proxy in
front before exposing it. The admin UI requires HTTPS in production
(`Secure` session cookies, strict CSP).

### traefik (shipped overlay)

1. In `.env`:
   ```bash
   COMPOSE_FILE=docker-compose.yml:compose.traefik.yml
   KLOPOT_HOSTNAME=alerts.example.com
   TRAEFIK_NETWORK=traefik            # the network your traefik container is on
   TRAEFIK_CERTRESOLVER=letsencrypt   # a resolver defined in traefik's static config
   ALERTD_TRUSTED_PROXY_CIDRS=…       # docker network inspect "$TRAEFIK_NETWORK" → Subnet
   ```
2. `docker compose up -d`. The container joins `TRAEFIK_NETWORK` under the
   alias `klopot`.
3. Route discovery depends on how your traefik is configured:
   - **docker provider** — nothing else to do; the labels in
     `compose.traefik.yml` define the router (TLS + HSTS).
   - **file provider** — copy [`deploy/traefik/klopot.example.yml`](../deploy/traefik/klopot.example.yml)
     into traefik's dynamic-config directory, set the hostname and
     `certResolver`. It targets `http://klopot:5090`.

`ALERTD_TRUSTED_PROXY_CIDRS` matters: without it, every login appears to
come from traefik's IP and the per-IP lockout locks out everyone at once.

### Other proxies

Caddy:

```
alerts.example.com {
    reverse_proxy 127.0.0.1:5090
    encode gzip
}
```

WebSocket endpoints (`/v1/stream/notifications`, `/v1/stream/state`)
require WebSocket support; Caddy and traefik handle this transparently.
Nginx requires `Upgrade` / `Connection` headers (standard config).

## Admin UI

alertd serves its own admin single-page app at **`/admin/`**
(`app/admin_ui/`, static files, no build step). It authenticates with
the browser-session cookie from `/v1/auth/login` (see
`docs/AUTH_MODEL.md`, "Browser sessions") and only ever calls the
public `/v1/*` API.

| Variable | Default | Meaning |
|----------|---------|---------|
| `ALERTD_ADMIN_UI_ENABLED` | `true` | Mount `/admin`. The API is unaffected either way. |
| `ALERTD_ADMIN_BOOTSTRAP_PASSWORD` | — | First-boot password for the `admin` account (≥ 12 chars); forced change at first login; clear afterwards. |
| `ALERTD_COOKIE_SECURE` | `true` in code, `false` in `docker-compose.yml` (localhost), forced `true` by `compose.traefik.yml` | Session cookies carry `Secure` — the UI must be served over HTTPS. `false` only for plain-HTTP localhost / development. |

### First login

1. Set `ALERTD_ADMIN_BOOTSTRAP_PASSWORD` (≥ 12 characters) in `.env` before the
   first start; it is used only while the `admin_users` table is empty.
2. Open `/admin/`, log in as `admin`, change the password when forced.
3. Remove `ALERTD_ADMIN_BOOTSTRAP_PASSWORD` from `.env` and recreate:
   `docker compose up -d alertd`.

Break-glass (lost password / locked out):

```bash
docker compose exec alertd python -m scripts.admin --username admin reset-password
docker compose exec alertd python -m scripts.admin --username admin unlock
```

The page sends a strict `Content-Security-Policy` (`script-src 'self'`
only). Do not put the UI behind a proxy that injects scripts.

## Logs

```bash
docker compose logs alertd
docker compose logs mysql
```

Set `ALERTD_LOG_FORMAT=json` for structured logs. Output goes to
Docker's `json-file` driver (`max-size: 10m`, `max-file: 5`).

## Resource limits

Recommended baseline:

```yaml
alertd:
  deploy:
    resources:
      limits:
        memory: 512M
        cpus: '1.0'
      reservations:
        memory: 256M
        cpus: '0.25'

mysql:
  deploy:
    resources:
      limits:
        memory: 1G
        cpus: '1.0'
```

At target load (37 inputs, ~1000 msgs/min, ~10 rules), alertd uses
~150 MB RSS and <5% of one CPU. Limits are 3-5× headroom for spikes.

## Upgrades

Single-version-at-a-time. The supported path for an existing install is
the deploy script, run from the checked-out release:

```bash
git pull
scripts/deploy.sh <label> --dry-run   # preflight + plan, changes nothing
scripts/deploy.sh <label>             # asks before it changes anything
```

It takes a gzip-verified full dump to `backups/alertd-predeploy-<label>-<UTC>.sql.gz`,
tags the image the running container uses as `rollback-pre-<label>`, builds,
recreates only the `alertd` container (MySQL is untouched; migrations run on
startup), waits for `/v1/health/ready`, then compares the schema revision
and config row counts with the pre-deploy snapshot and scans the startup log.
It prints the exact rollback command at the end.

Before deploying a release that adds a setting: put the variable in `.env`
**and** in the `environment:` list of `docker-compose.yml` — compose passes
only the variables listed there, so a value that exists only in `.env` is
silently ignored.

The manual equivalents, if you prefer them. CI publishes a prebuilt image
to GHCR on every green `main` build (`ghcr.io/sm26449/klopot` —
`:latest`, `:v<version>`, `:sha-<commit>`):

```bash
git pull                      # keep compose/env/scripts in sync
docker login ghcr.io          # once per host (PAT with read:packages)
docker compose pull alertd
docker compose up -d alertd   # mysql untouched
```

Fallback — build on the host (no registry access needed):

```bash
git pull
docker compose build alertd
docker compose up -d alertd
```

Migrations apply automatically at startup (fail-fast — see
Migrations above); running `alembic upgrade head` manually is
idempotent and safe.

For rollback after `scripts/deploy.sh`, re-point `:latest` at the tag it
created and recreate the container:

```bash
docker tag ghcr.io/sm26449/klopot:rollback-pre-<label> ghcr.io/sm26449/klopot:latest
docker compose up -d --no-deps alertd
```

Migrations are forward-only (see "Rollback — forward-only" above): if the
release applied a migration, the older code may refuse the newer schema, and
the rollback then also needs the pre-deploy dump restored (see "Backups").
