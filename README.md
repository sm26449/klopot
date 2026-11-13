<p align="center">
  <img src="docs/brand/social-preview.svg" alt="Klopot — alerts, declared once, delivered anywhere" width="640">
</p>

<h1 align="center">Klopot</h1>

<p align="center">
  <b>Declare an alert once. Deliver it anywhere.</b><br>
  A self-hosted, API-driven notification microservice — you declare inputs,
  rules, templates and channels; it evaluates and delivers, with throttling,
  retries and a full audit trail.
</p>

<p align="center">
  <a href="LICENSE">Apache-2.0</a> ·
  Python 3.12 · FastAPI · MySQL 8 ·
  <a href="README.ro.md">Română</a>
</p>

> **Naming.** The product is **Klopot**; the daemon, its image entry point and
> its `ALERTD_*` settings are still called `alertd` through 1.x. Klopot was
> born as the alerting service of a home-energy monitoring stack, but nothing
> in it is domain-specific.

---

Fire an alert from anything that can make an HTTP request — a script, a cron
job, Node-RED, another service. The caller needs only an API key and an alert
*type*; Klopot owns routing, channels and secrets:

```bash
curl -X POST https://your-host/v1/fire \
  -H "X-API-Key: $KLOPOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"type": "backup_failed", "context": {"job": "nightly-db", "error": "timeout"}}'
```

```json
{ "id": "ntf_1794139677372_7fc1…", "dispatched": true,
  "channels": ["ui_default", "telegram_oncall"], "status": "sent",
  "title": "Backup failed: nightly-db", "severity": "warning" }
```

## Works with

Delivery channels — add one by configuration, no code:

**UI (live WebSocket)** · **Telegram** · **SMS** (via a gateway) · **Email** ·
**Web Push** · **ntfy** · **Slack / Discord / Home Assistant** (generic webhook)

Inputs — where values come from: **MQTT** · **HTTP poll** · **inbound webhook**
· **inbound SMS** · **cron schedules**.

## Try it in two minutes

A self-contained demo (Klopot + MySQL + Mosquitto + a sine-wave sensor + a
webhook sink) that fires a real alert end to end:

```bash
git clone https://github.com/sm26449/klopot.git
cd klopot
docker compose -f compose.demo.yml up -d --build
./demo/smoke.sh          # asserts a notification reaches the sink within 2 min
docker compose -f compose.demo.yml down -v
```

## Run it for real

```bash
cp .env.example .env        # DB passwords, MQTT broker, admin password, channel secrets
docker compose up -d        # Klopot + MySQL + nightly backups, port 127.0.0.1:5090
open http://localhost:5090/admin/     # admin UI
open http://localhost:5090/docs       # OpenAPI / Swagger (open on plain-HTTP localhost)
```

Three compose variants ship with the repo:

| Variant | Command |
|---------|---------|
| Production, no proxy | `docker compose up -d` |
| Production behind traefik (TLS) | `docker compose -f docker-compose.yml -f compose.traefik.yml up -d` |
| Development (builds locally, bundled MQTT broker) | `docker compose -f docker-compose.yml -f compose.dev.yml up --build` |

Migrations run on startup. [Deploy](docs/DEPLOY.md) covers the traefik setup
(docker or file provider), backups and upgrades. Then follow
[Getting Started](docs/GETTING_STARTED.md), or import a ready-made pack from
[`examples/`](examples/) (uptime, IoT threshold).

## Features

- **API-first.** Every input, variable, rule, template, channel, route and
  schedule is a DB row, editable over REST. Live OpenAPI at `/docs`.
- **Rules.** A whitelisted expression language (no raw `eval`), N-of-N
  persistence, per-rule eval interval, Alertmanager-style inhibition.
- **Gating.** Enable flags, snooze (type / rule / channel), quiet hours,
  min-repeat throttling, duplicate coalescing.
- **Durable delivery (at-least-once).** A fire is persisted with a per-channel
  delivery row **before** any external send; a background worker retries
  failures with backoff and reconciles after a restart.
- **Observability.** Structured JSON logs, Prometheus `/v1/metrics`, request
  trace ids, and an audit log of every config change.
- **Admin UI** at `/admin` — a dependency-light, build-less SPA to manage it
  all, watch the live log, and test channels (keyboard-accessible, AA contrast).

## How it works, in one paragraph

Klopot subscribes to the declared inputs and keeps a live **state cache** of
variable values. Every few seconds it evaluates each enabled **rule** against
that cache; a rule that matches for its required consecutive ticks builds an
envelope for the **dispatcher**. The dispatcher applies gating, then persists a
`notifications_log` row **and** a `deliveries` row per routed channel in one
transaction *before* sending. It makes a synchronous first attempt; any channel
that fails retryably stays **pending** and a background **delivery worker**
retries it with backoff. Channel adapters enforce their own rate limits and
circuit breakers, and every config change is audited.

## Documentation

| Doc | What it covers |
|-----|----------------|
| **[Getting Started](docs/GETTING_STARTED.md)** · [RO](docs/GETTING_STARTED.ro.md) | Core concepts + an end-to-end walkthrough |
| **[API Reference](docs/API.md)** · [RO](docs/API.ro.md) | Every REST + WebSocket endpoint, auth, errors |
| [Deploy & Operations](docs/DEPLOY.md) | Install, env vars, backups, upgrades, rollback |
| [Architecture](docs/ARCHITECTURE.md) | Components, data flow, the transactional outbox |
| [Expression language](docs/EXPRESSION_LANGUAGE.md) | Rule condition syntax + built-in functions |
| [Examples](examples/) | Importable config packs |
| [All docs →](docs/README.md) | The full index |

## License & contributing

Licensed under the **Apache License 2.0** — see [LICENSE](LICENSE) and
[NOTICE](NOTICE). Bundled frontend runtime (vendored, build-less):
[Preact](https://preactjs.com) (MIT) · [htm](https://github.com/developit/htm)
(Apache-2.0).

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup and conventions,
[SECURITY.md](SECURITY.md) for reporting vulnerabilities, and
[CHANGELOG.md](CHANGELOG.md) for history.

---

## The team

Built by **[Stefan Maldaianu](https://github.com/sm26449)** — product owner,
operator and the person who gets paged at 02:00 — together with
**[Claude](https://claude.ai)** (Anthropic), pair-programmer across
architecture, code, audits, documentation and the Klopot brand.

Human judgement, machine stamina. The best team in the stack.
