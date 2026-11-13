# Changelog

All notable changes to Klopot are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] — Unreleased

First public release. Klopot grew out of the alerting service of a private
home-energy deployment, where it ran in production through many internal
iterations; that history is not carried over.

### Added

- **API-first configuration.** Inputs, variables, rules, templates, channels,
  routing and schedules are database rows, managed over a versioned REST API
  (`/v1/`) with a live OpenAPI document at `/docs`. Config export, validate
  and import as YAML or JSON (`/v1/config/*`).
- **Fire API.** `POST /v1/fire` lets any HTTP client raise an alert by type,
  with an idempotency window and API keys scoped `fire` / `read` / `ack` /
  `admin`.
- **Inputs:** MQTT, HTTP polling, token-gated inbound webhooks and an SMS
  inbox.
- **Channels:** Telegram, email (SMTP), SMS via an HTTP gateway, generic
  webhooks (with presets such as ntfy), Web Push (VAPID), and the in-app
  UI/banner channel. Per-channel circuit breaker and rate limiting.
- **Rules engine.** A sandboxed, whitelisted expression language (no raw
  `eval`), N-of-N persistence, per-rule evaluation interval, computed and
  aggregate variables, and Alertmanager-style inhibition.
- **Gating.** Enable flags, snooze (by type, rule or channel), quiet hours,
  minimum-repeat throttling, duplicate coalescing, escalation of
  unacknowledged critical alerts, and a daily digest of suppressed alerts.
- **Durable, at-least-once delivery.** Each fire is persisted with a delivery
  row per channel before any external send; a background worker retries with
  backoff and reconciles after a restart.
- **Admin UI** at `/admin`: a build-less Preact single-page app to manage
  everything, watch the live notification log over WebSocket and test
  channels. Session login with lockout, CSRF protection and a strict
  Content-Security-Policy; keyboard-accessible with WCAG AA contrast;
  English and Romanian; light/dark Klopot theme plus optional OS-native theme
  families.
- **Security hardening.** SSRF screening and IP pinning on every outbound
  HTTP call, secrets referenced by environment-variable name (never stored in
  the database), credential redaction in logs and API output, request size
  caps, and ReDoS-safe regular expressions.
- **Observability.** Structured JSON logs, Prometheus metrics at
  `/v1/metrics`, request trace ids, readiness/liveness health endpoints and an
  audit log of every configuration change.
- **Deployment.** Docker image, MySQL 8 with Alembic migrations applied on
  startup, a backup sidecar, and three compose variants — production,
  production behind traefik (docker or file provider), and development — plus
  a self-contained two-minute demo (`compose.demo.yml`).
- **Examples.** Importable config packs in `examples/` (uptime monitoring and
  an IoT threshold alert).

[Unreleased]: https://github.com/sm26449/klopot/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/sm26449/klopot/releases/tag/v1.0.0
