# Project status — 2026-11-15

**1.1.1** (2026-11-15) is the current release; `pyproject.toml` and
`GET /v1/version` say `1.1.1`. The [changelog](../CHANGELOG.md) has its
upgrade notes (no default passwords; escalation needs a named channel), and
builds of later commits are grouped there under **Unreleased** (they still
report `1.1.1` until the next release). See
[INTEGRATIONS_ROADMAP.md](INTEGRATIONS_ROADMAP.md) for the remaining
integrations.

## 1.0.1 baseline

Released 2026-11-14.
The baseline ships schema `0027`.

| Area | Delivered behaviour | Reference |
|------|---------------------|-----------|
| Delivery visibility | Per-channel purpose, outcome, retry count, next attempt and errors in the log drawer/API | [API](API.md#alerts-log) |
| Durable escalation | Persist before send, bounded retries, separate initial/escalation rollups and cancellation after acknowledgement | [Architecture](ARCHITECTURE.md#durable-escalation) |
| Rule incidents | Opt-in episodes, acknowledgement separate from resolution, hysteresis and recovery notices | [Incidents](INCIDENTS.md) |
| Telegram actions | Dedicated-bot long polling, actor policy, opaque expiring buttons, durable ACK/snooze and independent keyboard cleanup | [Telegram](TELEGRAM.md) |
| MQTT output | Persistent connections, reconnect, QoS, JSON templates, stable delivery identity, availability/LWT and heartbeat | [MQTT output](MQTT_OUTPUT.md) |
| Monitoring | Operations UI/API, durable queues, worker/connection state, metrics, Grafana dashboard and Prometheus examples | [Operations](OPERATIONS.md) |

Migrations `0024`–`0027` preserve existing configuration. Incidents and Telegram
actions require explicit opt-in. Adding MQTT support does not add routes to
existing templates.

## 1.1.0 — work since the 1.0.1 baseline

Released as 1.1.0 on 2026-11-15, with schema `0039`; every migration
preserves existing configuration.

| Area | What it adds | Migration | Reference |
|------|--------------|-----------|-----------|
| Admin UI and API ergonomics | API reference page and `x-required-scope`; rule `eval_status`; icon validation; rules/variables grouping, usage and bulk actions; Ctrl+K search; teaching empty states | — | [Admin UI](ADMIN_UI.md), [API](API.md) |
| Selective import / export | Per-section export, item-by-item import with preview / apply | — | [Admin UI](ADMIN_UI.md) |
| Shared fire service, external episodes | Every entry point goes through one service; episode lifecycle on `POST /v1/fire` | `0028` | [Incidents](INCIDENTS.md) |
| Alertmanager / Grafana receiver, native ntfy | `kind: alertmanager` input; `kind: ntfy` channel | `0028` | [API](API.md) |
| Gotify, Pushover, provider lifecycle | Native channels; durable `lifecycle_commands` and deduplicated `inbound_events` (Pushover emergency cancelled on acknowledgement and vice versa); `intrusive` flag; adapter test kit | `0029` | [Architecture](ARCHITECTURE.md) |
| Client SDKs | Python `klopot-client`, TypeScript `@klopot/client`, drift-checked against `openapi/v1.json` | — | [sdk/README.md](../sdk/README.md) |
| Generic delivery gate | Per-template `gate_variable` / `gate_min` replaces the domain-specific setting | `0030` | [API](API.md) |
| SMS providers | `http`, `twilio`, `teltonika`; old gateway shape converted | `0031` | [API](API.md) |
| Packs and setup guide | Installable configuration packs with parameters, a catalog and export as a pack; first-run setup guide | — | [Packs](PACKS.md) |
| Delivery semantics and secrets | `Retry-After` backpressure, permanent refusals, idempotency keys for gateways; `KLOPOT_SECRET_*` references and an optional `secrets.env` | — | [Deploy](DEPLOY.md) |
| Activity log | Requests, provider attempts with their HTTP exchange, state changes; editable keep / ignore rules; Activity page | `0032` | [Activity log](ACTIVITY_LOG.md) |
| Web Push | Installable admin UI, per-device subscriptions with minimum severity and pause | `0033` | [Web Push](WEB_PUSH.md) |
| Pre-release audit fixes | Concurrent fires of one type no longer deadlock on MySQL; provider credentials and destination paths kept out of the activity log; wrong API keys bounded and keys found by an indexed digest; Web Push devices not paused by a local outage; non-finite numbers stored as `null`; suppressed external episodes announced by a later firing; backup script fails on a failed dump; delivery lookup indexed | `0034`, `0035` | [Changelog](../CHANGELOG.md) |
| Second pre-release review | Episode keys case-sensitive on MySQL; long messages and lone surrogates no longer lose an alert; render, preview and expression CPU bounds; acknowledgement / worker deadlock; breaker probe released on cancellation; sign-in returns its DB connection before hashing; delivery errors scrubbed of channel secrets; inbound webhook checks the token first; push pause reason recorded; Pushover receipts polled through an index; rollup repair; SMTP pinned, MQTT brokers screened; tag-based image publishing | `0036`–`0039` | [Changelog](../CHANGELOG.md#upgrade-notes) |

## Verifying a deployment

This document makes no claim about what any particular installation runs.
To see what a deployment actually serves, check all three:

- `GET /v1/version` — the application version (stays `1.1.0` for builds of
  later commits until the next release is cut);
- `docker inspect <container>` — the image and its tag or digest;
- `SELECT version_num FROM alembic_version` — the applied schema revision
  (compare with the highest file in `alembic/versions/`).

## Validation

**1.1.0 release gate (2026-11-15, after the second pre-release review).**
All of the following passed:

- Ruff; no new mypy violations against the existing baseline.
- pytest on in-memory SQLite: 1538 tests.
- Node admin-UI tests: 393.
- OpenAPI drift and SDK drift checks; gitleaks.
- pytest MySQL gate on a disposable MySQL 8: 1551 tests.
- Browser end-to-end suite against a throwaway fresh install (schema 0001 →
  0039): 89 tests.
- Every rule expression of the production instance validates under the
  tightened expression bounds.

**1.0.1 baseline.** Completed before/around its release:

- Backend suites on in-memory SQLite and disposable MySQL, plus focused
  destination-freezing/authentication tests; 311 admin-UI tests.
- Ruff passed; no new mypy violations against the existing baseline.
- OpenAPI compatibility check found no breaking changes from the prior baseline.
- Live dedicated-bot ACK and one-hour snooze, including actor audit and keyboard cleanup.
- Real Mosquitto delivery, stable replay identity, retain disabled by default,
  reconnect after broker restart, retained availability and graceful shutdown.
- Built-image readiness, version, migrated schema, HTTP-to-MQTT delivery,
  operational snapshots and metrics.
- Prometheus scrape configuration and eight alert rules validated with promtool;
  staged files scanned without secret findings; no local env files in the image.
- A production backup restored on disposable MySQL; migration `0023 → 0027`
  preserved row counts and channel configuration.

Production uses **MySQL 8 only**. SQLite is a fast test harness, not a runtime
datastore or fallback. The MySQL gate and real migration/restore checks cover
behaviour SQLite cannot establish. See [CONTRIBUTING.md](../CONTRIBUTING.md#tests).

## Remaining work and deployment choices

Publishing the SDKs to PyPI / npm is pending. Action buttons in Web Push
notifications are a later phase. The next integration in the existing order is
PagerDuty; a Multi-Bus Gateway (MBG) input, Signal and OIDC remain later work. The
Prometheus query preset, IMAP, Helm, Home Assistant add-on and other
demand-driven items remain in the
[roadmap](INTEGRATIONS_ROADMAP.md#6-suggested-order-and-rough-calendar).

Grafana import/datasource selection, Prometheus scrape/rule loading, MQTT
channel routing, Telegram actor/chat configuration and Web Push (VAPID key)
are per-installation choices. Availability of code or a dashboard file does
not establish that each installation has enabled it. Integration setup
remains in the linked feature guides; credentials and private chat
identifiers do not belong here.
