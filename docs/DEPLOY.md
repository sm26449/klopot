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
goals. The service targets a few dozen declared inputs at <1000 msgs/min;
one Python process is plenty.

### How we enforce it

In `Dockerfile`:
```
gunicorn ... --workers 1 ...
```

`docker-compose.yml` starts one `alertd` container. That is a convention,
not a lock: nothing stops `--scale alertd=2`, or a second container
started by hand against the same database, and it would evaluate the same
rules and notify twice. Do not do that.

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
| `compose.traefik.yml` | **Overlay** — joins an existing traefik's Docker network (`TRAEFIK_NETWORK`, alias `klopot`), adds docker-provider labels for `KLOPOT_HOSTNAME` with TLS + HSTS, forces `ALERTD_COOKIE_SECURE=true`. **Private**: only `KLOPOT_PRIVATE_CIDRS` (default: loopback + private ranges) may reach it; requires `ALERTD_TRUSTED_PROXY_CIDRS`. |
| `compose.public.yml` | **Overlay on `compose.traefik.yml`** — opens exactly `POST /v1/fire` to any address, with a rate, concurrency and body limit. See "Exposing /v1/fire to the internet". |
| `compose.external-db.yml` | **Overlay** — use an existing MySQL server instead of the bundled one: `mysql` and `backup` are not started; `ALERTD_DATABASE_URL` points at your server. |
| `compose.dev.yml` | **Overlay** — builds from the checkout (`klopot:dev`), bundles an anonymous Mosquitto on `127.0.0.1:1883`, DEBUG logs, insecure cookies, `/docs` + `/v1/metrics` open, no backup sidecar (`--profile backup` to add it). |
| `compose.demo.yml` | **Standalone** two-minute demo (MySQL on tmpfs, publisher, webhook sink). |

```bash
docker compose up -d                                                 # production
docker compose -f docker-compose.yml -f compose.traefik.yml up -d    # production behind traefik (private)
docker compose -f docker-compose.yml -f compose.traefik.yml -f compose.public.yml up -d   # + POST /v1/fire public
docker compose -f docker-compose.yml -f compose.dev.yml up --build   # development
```

Set `COMPOSE_FILE` in `.env` (e.g. `COMPOSE_FILE=docker-compose.yml:compose.traefik.yml`)
so plain `docker compose …` commands — and `scripts/deploy.sh` /
`scripts/bootstrap.sh` — always address the right variant. Host-specific
tweaks (extra network aliases, mounts) belong in a `compose.local.yml`
(gitignored) appended to the same list.

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
--build`, and waits for `/v1/health/ready` on the port this install
publishes (`KLOPOT_HTTP_PORT` from `.env`, default 5090; `deploy.sh` and
`restore_drill.sh` check the same port, `ALERTD_URL` overrides it). It is
idempotent.

State after the first start:
- `alertd` auto-applies Alembic migrations at startup (fail-fast: a failed
  upgrade aborts startup and the container restart-loops visibly rather
  than running on a stale schema).
- `mysql` creates the `alertd` database if absent.
- Only the bootstrap rows exist: `ui_default` + `banner_default` channels,
  default settings, the `admin` login (if `ALERTD_ADMIN_BOOTSTRAP_PASSWORD`
  is set) and the admin API key (if `ALERTD_BOOTSTRAP_ADMIN_KEY` is set).
  Rules, templates and channels are yours to create — in the admin UI, over
  the API, or by installing a pack (Admin UI → Packs, or `POST /v1/packs/apply`
  — see [PACKS.md](PACKS.md)). The `self-monitoring` pack (Klopot's own
  alerts) is installed automatically.

### Environment variables

See `.env.example`. The main ones:

> **Compose passes only listed variables.** `docker-compose.yml` hands the
> `alertd` container the variables in its `environment:` list (plus
> `secrets.env`). Every `ALERTD_*` setting of `app/config.py` is in that list
> with the same default (`tests/test_compose_env.py` keeps them in step), so
> setting one in `.env` is enough.

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
| `ALERTD_DATABASE_URL` | — (required; Klopot refuses to start without it) | Async SQLAlchemy URL, e.g. `mysql+aiomysql://alertd:<MYSQL_PASSWORD>@mysql:3306/alertd` |
| `ALERTD_MQTT_HOST` | `host.docker.internal` in compose, `localhost` in code | Broker hostname |
| `ALERTD_MQTT_PORT` | `1883` | |
| `ALERTD_MQTT_USERNAME` | (empty) | Optional |
| `ALERTD_MQTT_PASSWORD` | (empty) | Optional |
| `ALERTD_MQTT_CLIENT_ID` | `alertd` | Visible in broker connection list |
| `ALERTD_LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `ALERTD_LOG_FORMAT` | `console` | `console` / `json` |
| `ALERTD_TZ` | `UTC` | Timezone for hour_now()/in_window() |
| `ALERTD_LATITUDE`, `ALERTD_LONGITUDE` | (empty) | Place of the install in degrees (north / east positive), for `sun_elevation()` and `is_daylight()` in rule conditions; without them those functions are an evaluation error |
| `ALERTD_PV_POWER_VAR` | (empty) | **Deprecated.** Before migration 0030 every template's `require_pv_kw` compared against this one variable. Now each template names its own `gate_variable`; this value is read only by migration 0030 to convert existing templates, and when an old client writes `require_pv_kw` without a variable. |
| `ALERTD_HASH_MAX_CONCURRENCY` | `4` | Max concurrent password/API-key hashing ops offloaded to threads (bounds CPU + argon2 memory on an auth burst). |
| `ALERTD_MAX_AGGREGATE_MEMBERS` | `1000` | Per-aggregate member budget (audit D1-01). Expired members are evicted; at the budget a new member is refused and the aggregate output invalidated (surfaced by the `alertd_aggregate_overflow` metric), never silently trimmed. `0` = unbounded. |
| `ALERTD_MQTT_QUEUE_MAX` | `10000` | Finite MQTT incoming-queue capacity (audit D1-02). The adapter subscribes to the configured filters, not `#`. On overflow aiomqtt drops (QoS0); a missed update degrades to staleness and a reconnect redelivers retained state. |
| `ALERTD_MQTT_MAX_PAYLOAD_BYTES` | `262144` | Drop (and count, in input health `dropped_oversized`) an MQTT payload larger than this before decode. |
| `ALERTD_MAX_REQUEST_BYTES` | `1048576` | Global inbound request-body cap (audit A-08). An ASGI middleware refuses a larger body with `413` before any handler buffers it. |
| `ALERTD_MAX_WEBHOOK_BYTES` | `65536` | Tighter cap for the public token-gated webhook-ingress endpoint; outsized bodies are rejected before parsing. |
| `ALERTD_MAX_ALERTMANAGER_BYTES` | `1048576` | Cap for an Alertmanager / Grafana alert group posted to an `alertmanager` input (groups are larger than webhook values; still bounded by `ALERTD_MAX_REQUEST_BYTES`). |
| `ALERTD_MAX_RESPONSE_BYTES` | `4194304` | Decompressed byte cap on an upstream HTTP-poll / webhook response, so a huge or compression-bomb body can't exhaust memory. |
| `ALERTD_MAX_CONFIG_DEPTH` | `50` | Max YAML/JSON nesting depth for config import. Aliases/anchors are rejected outright (billion-laughs). |
| `ALERTD_BOOTSTRAP_ADMIN_KEY` | (empty) | One-time admin API key seeded on first run |
| `TELEGRAM_BOT_TOKEN` | (empty) | Telegram channel secret (resolved via `*_ref` in channel config) |
| `SMTP_PASSWORD` | (empty) | Email channel secret (via `*_ref`) |
| `SMS_GATEWAY_API_KEY` | (empty) | SMS gateway secret (via `*_ref`) |
| `ALERTD_EXTERNAL_ALARM_TOKEN` | (empty) | Example webhook-input token (`auth_token_ref`); on the built-in `*_ref` allowlist, like the three above and `ALERTD_MQTT_USERNAME` / `ALERTD_MQTT_PASSWORD` |
| `KLOPOT_SECRET_<NAME>` | — | Any other secret a channel, input or pack references, in **`secrets.env`** (see below). Always allowed as a `*_ref`. |
| `ALERTD_ACTIVITY_LOG_BODIES` | `true` | `false` keeps every activity-log row but no request / response bodies (docs/ACTIVITY_LOG.md). What is kept per request is otherwise set with activity rules in the admin UI. |
| `ALERTD_PUSH_ALLOWED_HOSTS` | — | Extra Web Push services besides Apple / Google / Mozilla / Microsoft, comma-separated (`*.example.com` allowed). Only for a self-hosted push service (docs/WEB_PUSH.md). |
| `ALERTD_SECRET_REF_ALLOW` | (empty) | Extra variable names a `*_ref` may resolve, comma-separated. Rarely needed — prefer `KLOPOT_SECRET_*`. |
| `BACKUP_KEEP_DAYS` | `30` | Backup sidecar rotation |
| `BACKUP_CRON` | `0 2 * * *` | Backup sidecar schedule: minute and hour, each `*`, a number or `*/N` (other fields ignored) |
| `MYSQL_ROOT_PASSWORD` | — (required) | DB container only |
| `MYSQL_INNODB_BUFFER_POOL_SIZE` | `256M` | DB container only |
| `MYSQL_DATABASE` | `alertd` | DB container only |
| `MYSQL_USER` | `alertd` | DB container only |
| `MYSQL_PASSWORD` | — (required with the bundled MySQL) | DB container only; also goes into `ALERTD_DATABASE_URL` |

Other knobs, all documented in `app/config.py`:

- Set them in `.env`: the session /
  login-lockout settings (`ALERTD_SESSION_IDLE_HOURS`, `ALERTD_SESSION_MAX_DAYS`,
  `ALERTD_LOGIN_MAX_FAILURES`, `ALERTD_LOGIN_MAX_FAILURES_PER_USER`, `ALERTD_LOGIN_MAX_FAILURES_PER_IP`,
  `ALERTD_LOGIN_LOCKOUT_MIN`), `ALERTD_TRUSTED_PROXY_CIDRS`,
  `ALERTD_FIRE_CONTEXT_MAX_BYTES` (16384 — the largest `context` `/v1/fire`
  accepts, as compact JSON; nesting is capped at 16 levels),
  `ALERTD_DOCS_ENABLED` / `ALERTD_METRICS_REQUIRE_AUTH` (blank = auto),
  `ALERTD_ADAPTER_SEND_TIMEOUT_SEC` (30) and the admission caps
  `ALERTD_MAX_RULES` (100), `ALERTD_MAX_INPUTS` (50), `ALERTD_MAX_CHANNELS` (20).
- Tuning and retention: `ALERTD_DATABASE_POOL_SIZE` (10),
  `ALERTD_DATABASE_MAX_OVERFLOW` (5), `ALERTD_MQTT_KEEPALIVE_SEC` (60),
  `ALERTD_DEFAULT_EVAL_INTERVAL_SEC` (10), `ALERTD_IDEMPOTENCY_WINDOW_SEC` (300),
  `ALERTD_LOG_RETENTION_DAYS` (90), `ALERTD_AUDIT_RETENTION_DAYS` (365),
  `ALERTD_AUTH_HISTORY_DAYS` (30), `ALERTD_CIRCUIT_BREAKER_THRESHOLD` (3),
  `ALERTD_CIRCUIT_BREAKER_OPEN_SEC` (60), `ALERTD_EVAL_ERROR_DISABLE_THRESHOLD`
  (50), `ALERTD_ESCALATION_AFTER_MIN` (15), `ALERTD_ESCALATION_CHANNEL`
  (empty = escalation off; name the channel to re-page through), `ALERTD_DIGEST_HOUR` (21), `ALERTD_SNOOZE_MORNING_HOUR` (8), `ALERTD_CORS_ORIGINS` (empty),
  `ALERTD_BLOCK_PRIVATE_EGRESS` (`false`), `ALERTD_ACTIVITY_QUEUE_MAX` (5000).

### Secrets for channels, inputs and packs (`secrets.env`)

A secret field of a channel, input or pack takes either a literal value or
the **name** of an environment variable (`*_ref`), whose value Klopot reads
at send time. A literal typed into the admin UI or the API **is stored in the
database** — and so in every database backup and dump. A ref keeps the
secret out of both; use refs in production. For every secret beyond the
built-in ones above, use one file:

```bash
cp secrets.env.example secrets.env && chmod 600 secrets.env
# one line per secret, the name must start with KLOPOT_SECRET_
echo 'KLOPOT_SECRET_GOTIFY_TOKEN=AbCdEf…' >> secrets.env
docker compose up -d alertd          # restart so the container sees it
```

Then, in the channel (Secret field → "Use env ref…") or the pack setting,
enter `KLOPOT_SECRET_GOTIFY_TOKEN`. `docker-compose.yml` loads `secrets.env`
into the `alertd` service only (optional file — absent is fine). A
`KLOPOT_SECRET_*` name is accepted automatically; any other name must be
listed in `ALERTD_SECRET_REF_ALLOW`, so a reference can never read a process
secret such as `ALERTD_DATABASE_URL`. The Packs page shows, before you
install, whether each secret a pack needs is already set.

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

The container's healthcheck probes `/v1/health/ready` every 30s; the container
is marked unhealthy if three consecutive probes fail. Readiness returns HTTP
503 for a failed essential component (database, engine or delivery worker).

`/v1/health` is the informational endpoint and always returns HTTP 200; inspect
its body for `ok` / `degraded` / `down` (the component map needs a `read` key).
An unhealthy Docker status does not by
itself restart a running process. See [OPERATIONS.md](OPERATIONS.md) for
monitoring and [PROJECT_STATUS.md](PROJECT_STATUS.md) for release/deployment state.

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
   #KLOPOT_PRIVATE_CIDRS=…            # who may reach Klopot (default below)
   ```
2. `docker compose up -d`. The container joins `TRAEFIK_NETWORK` under the
   alias `klopot`.
3. Route discovery depends on how your traefik is configured:
   - **docker provider** — nothing else to do; the labels in
     `compose.traefik.yml` define the router (TLS + HSTS + the private allowlist).
   - **file provider** — copy [`deploy/traefik/klopot.example.yml`](../deploy/traefik/klopot.example.yml)
     into traefik's dynamic-config directory, set the hostname,
     `certResolver` and the private networks. It targets `http://klopot:5090`.

**Private by default.** The hostname answers only clients whose address is
in `KLOPOT_PRIVATE_CIDRS` — by default loopback and the private ranges
(`10/8`, `172.16/12`, `192.168/16`, `fc00::/7`), i.e. a LAN or a VPN. Anyone
else gets `403` from traefik before reaching Klopot: the admin UI, login,
every API route, the live streams, `/docs` and `/v1/metrics` included. Set
`KLOPOT_PRIVATE_CIDRS` to your own networks (comma-separated) to narrow it;
widening it to the whole internet is never needed — open only `/v1/fire`
(next section). The list is matched against the address **traefik** sees:
with a CDN in front, that is the CDN.

**`ALERTD_TRUSTED_PROXY_CIDRS` is required** with this overlay (the compose
file refuses to start without it): it is traefik's address as Klopot sees it.
Without it every request appears to come from traefik, so one client's failed
logins or wrong API keys lock everyone out. An entry that is not an address or
network, or a `/0` (which would let any client choose its own address), stops
Klopot at startup with the entry named. The same list decides whose
`X-Forwarded-Proto` counts: from these proxies only, it gives the scheme the
client used, so a redirect (a trailing slash) keeps `https`. Klopot does this
itself — the image's gunicorn worker (`app.worker.KlopotWorker`) leaves proxy
headers alone and sends no `Server` header.

**A second layer inside Klopot: `ALERTD_ADMIN_ALLOW_CIDRS`** (comma-separated
networks; empty = off). When set, Klopot itself refuses everything but
`POST /v1/fire` and `POST /v1/inputs/{id}/webhook` to clients outside these
networks — `403` over HTTP, the WebSocket closed before it is accepted —
whatever the proxy lets through (a published port, a misrouted hostname).
It judges the real client address (behind `ALERTD_TRUSTED_PROXY_CIDRS`, the
one traefik forwarded), so list your admins' networks **and** the Docker
network of the services that call Klopot directly (on pv-stack:
pv-stack-ui on `pv-stack-network`, e.g.
`ALERTD_ADMIN_ALLOW_CIDRS=192.168.1.0/24,172.20.0.0/16,127.0.0.1`). An
invalid entry or a `/0` stops Klopot at startup.

### Exposing /v1/fire to the internet

Scripts and services elsewhere can send alerts without a VPN: add
`compose.public.yml` on top of the traefik overlay.

```bash
COMPOSE_FILE=docker-compose.yml:compose.traefik.yml:compose.public.yml
```

It opens **exactly** `POST /v1/fire` (not `/v1/fire/`, not another method,
not another path) to every address; everything else stays private. In front
of Klopot, traefik applies:

| Limit | Default | `.env` |
|-------|---------|--------|
| Requests per minute per client address | 60, bursts of 20 | `KLOPOT_PUBLIC_RATE_PER_MIN`, `KLOPOT_PUBLIC_BURST` |
| Requests in progress, all clients together | 16 | `KLOPOT_PUBLIC_MAX_INFLIGHT` |
| Request body | 64 KiB (`413` beyond) | `KLOPOT_PUBLIC_MAX_BODY` |

Before you open it:

- **One key per caller, scope `fire` only** (Admin UI → API keys), with an
  expiry. A `fire` key can send alerts and nothing else; revoke it alone if it
  leaks. Never use an admin key from outside.
- **Limit each key to its caller's addresses** (the key's "Allowed
  addresses", docs/AUTH_MODEL.md "Source allowlist"): a key copied elsewhere
  then gets `403`, and its attempts count toward that address's wrong-key
  limit.
- **Give each public key a rate limit** (its "Requests per minute",
  docs/AUTH_MODEL.md "Rate limit"): the proxy limits each address, the key's
  own limit caps one caller however many addresses it uses.
- **Set a read timeout on traefik's entrypoint** (static configuration, not a
  label), so a slow upload cannot hold a connection open:
  ```yaml
  entryPoints:
    websecure:
      transport:
        respondingTimeouts:
          readTimeout: 15s
  ```
- **Behind a CDN** (Cloudflare…): traefik sees the CDN's address. Set
  traefik's entrypoint `forwardedHeaders.trustedIPs` to the CDN's published
  ranges and add the same ranges to `ALERTD_TRUSTED_PROXY_CIDRS`, so Klopot's
  per-client controls see the visitor. Traefik's per-client rate limit counts
  the CDN's address unless you also set its `sourceCriterion.ipStrategy`;
  rely on the CDN's own rate rules in that case.
- The inbound inputs (`/v1/inputs/{id}/webhook`) are **not** opened by this
  overlay; keep their senders on the private network for now.

The routing was checked against traefik v3: `POST /v1/fire` passes, a GET,
`/v1/fire/`, `/admin/`, `/v1/stream/*` and the inputs get `403` from outside
the private networks, a body over the limit gets `413`, and requests above the
rate get `429`.

### Other proxies

Caddy:

```
alerts.example.com {
    reverse_proxy 127.0.0.1:5090
    encode gzip
}
```

Whatever the proxy, a TLS deployment needs two settings in `.env` (the
traefik overlay sets the first for you; the base compose file is for
localhost and sets it to `false`):

```bash
ALERTD_COOKIE_SECURE=true          # Secure session cookies; also takes /docs and
                                   # /v1/metrics out of public reach (see below)
ALERTD_TRUSTED_PROXY_CIDRS=…       # the address the proxy connects from, as the
                                   # container sees it — for a proxy on the host:
                                   # docker network inspect <compose network> → Subnet
```

Without `ALERTD_TRUSTED_PROXY_CIDRS` every request appears to come from the
proxy: one client's failed logins lock everyone out, and one client's wrong
API keys use up everyone's budget (5 a minute, then `429`).

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

### Web Push — alerts on phones without an app

The admin UI installs as an app (manifest + service worker) and receives Web
Push; an iPhone / iPad (iOS 16.4+) gets it from the app added to the Home
Screen. Design and limits: [WEB_PUSH.md](WEB_PUSH.md).

1. Generate the key once and keep it — changing it means every device has to
   enable notifications again:

   ```bash
   docker compose exec alertd python scripts/vapid_keys.py
   ```

   Put the `KLOPOT_SECRET_VAPID_PRIVATE=…` line in `secrets.env` and
   recreate: `docker compose up -d alertd`.
2. Admin UI → Channels → add a channel of kind **Web Push**: VAPID private →
   *Use env ref…* → `KLOPOT_SECRET_VAPID_PRIVATE`; subject
   `mailto:you@example.com`. Route templates to it like any channel.
3. On each phone / computer: open Klopot (on iPhone: Share → *Add to Home
   Screen*, then open it from there), sign in, Account → **Enable
   notifications**, then *Send a test*.

The UI must be served over HTTPS with a certificate the phone trusts. The
notification travels through Apple / Google, end-to-end encrypted, and
carries the alert text; tapping it opens Klopot, which needs the phone to
reach your Klopot URL (LAN, VPN or public).

## Logs

The admin Operations page, `/v1/operations`, Prometheus metrics and the portable
Grafana dashboard are described in [OPERATIONS.md](OPERATIONS.md). Native MQTT
output setup, including availability and heartbeat, is in [MQTT_OUTPUT.md](MQTT_OUTPUT.md).

```bash
docker compose logs alertd
docker compose logs mysql
```

Set `ALERTD_LOG_FORMAT=json` in `.env` for structured logs. Output goes to
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

At target load (a few dozen inputs, ~1000 msgs/min, ~10 rules), alertd uses
~150 MB RSS and <5% of one CPU. Limits are 3-5× headroom for spikes.

## Upgrades

Single-version-at-a-time. Read the release's **upgrade notes** in the
[changelog](../CHANGELOG.md#upgrade-notes) first — 1.1.0 runs migrations
`0028`–`0039` and changes a few behaviours an operator can see. The supported
path for an existing install is the deploy script, run from the checked-out
release (`git checkout v<version>`):

```bash
git pull
scripts/deploy.sh <label> --dry-run   # preflight + plan, changes nothing
scripts/deploy.sh <label>             # asks before it changes anything
```

**Skipping releases and rolling back.** You may jump several releases in one
deploy, but read the upgrade notes of **each** release you skip, not only the
newest. A release that runs a migration cannot be rolled back by redeploying
the older image alone: the old code may refuse the newer schema, so a rollback
past it also needs the pre-deploy database backup restored. `deploy.sh` takes
that backup and prints its path and the rollback command; keep both until the
new release has proved itself.

It takes a gzip-verified full dump to `backups/alertd-predeploy-<label>-<UTC>.sql.gz`,
tags the image the running container uses as `rollback-pre-<label>`, builds,
recreates only the `alertd` container (MySQL is untouched; migrations run on
startup), waits for `/v1/health/ready`, then compares the schema revision
and config row counts with the pre-deploy snapshot and scans the startup log.
It prints the exact rollback command at the end.

**Separate runtime directory.** If `.env`, the compose files and `backups/`
live outside the checkout (e.g. a source clone in `~/klopot` and the running
install in `/opt/klopot`), point the script at that directory:

```bash
scripts/deploy.sh <label> --runtime-dir=/opt/klopot --dry-run
scripts/deploy.sh <label> --runtime-dir=/opt/klopot
```

It then builds the image from the checkout as `<repo>:<label>` (e.g.
`klopot:1.0.2`), saves the runtime `.env` to `backups/env-predeploy-…`, sets
`KLOPOT_IMAGE` to the new image and recreates the container from the runtime
directory. Rollback = put the previous `KLOPOT_IMAGE` (or the
`rollback-pre-<label>` tag) back and `docker compose up -d --no-deps alertd`.
With `compose.external-db.yml` there is no `mysql` compose service, so also set
`ALERTD_MYSQL_CONTAINER=<mysql container name>` (the backup dumps only the
Klopot database).

Before deploying a release that adds a setting: put the variable in `.env`
**and** in the `environment:` list of `docker-compose.yml` — compose passes
only the variables listed there, so a value that exists only in `.env` is
silently ignored.

The manual equivalents, if you prefer them. CI publishes prebuilt images to
GHCR (`ghcr.io/sm26449/klopot`): a release tag publishes `:v<version>` and
`:latest`; a release candidate (`v1.3.0-rc.1`) publishes `:v<version>` only —
never `:latest` ([RELEASING.md](RELEASING.md)); every green `main` build
publishes `:edge`; each also gets `:sha-<commit>`. Pin `:v<version>` in
production — it always names one build:

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
