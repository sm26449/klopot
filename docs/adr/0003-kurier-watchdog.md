# ADR-0003 — Kurier watches Klopot: the `kurier` SMS provider and its watchdog ping

Status: Accepted
Date: 2026-11-17

## Context

Klopot cannot report its own outage through itself. If the process dies, the
container stops or the rule engine stalls while the process stays up (the
2026-11-17 improvements review, IP-01), no notification goes out and nobody
knows. `/v1/health/ready` does not see a stalled engine; the Prometheus rules
in `contrib/` would, but only where someone runs Prometheus with an alert path
that does not go through Klopot.

Kurier (sm26449/kurier) is the SMS gateway Klopot already sends through. It
runs as its own service and sends over LTE, so it survives a Klopot outage and
an internet outage. Kurier ADR-0001 gives it generic watchdogs: a service
pings `POST /api/watchdogs/{name}/ping`; silence, or a ping that says `fail`,
becomes an SMS. Klopot should use that — configured where the operator
already configures Kurier: the SMS channel. Kurier stays a separate service;
nothing of it moves into Klopot's code.

## Decision

1. **A `kurier` SMS provider** next to `http`, `twilio` and `teltonika`
   (`app/channels/sms_config.py`): Kurier's base URL, its key (`api_key_ref`),
   the phone number, and sends through Kurier's own API
   (`POST {url}/api/sms/send`). The generic `http` provider and the pre-0031
   shape keep working; switching the existing channel is one edit.
2. **A watchdog section on that channel** — "Kurier watches this Klopot":
   on/off (default off), `timeout_sec` (default 180), recipients (default:
   Kurier's own `SMS_WATCHDOG_TO`; the channel's phone if set there). The
   watchdog name is `klopot-<channel name>`.
3. **A small task of its own pings every 60 s** — not the rule engine, which
   must not wait on the network. `status` is Klopot's real health: `fail` with
   a reason when the engine's last tick is older than three intervals, the
   delivery queue is overdue, or a worker is down; else `ok`. A dead process
   sends nothing (Kurier alerts after `timeout_sec`); a stuck engine sends
   `fail` (Kurier alerts at once).
4. **The response is the handshake back.** From it Klopot raises two episodes
   of its own, as `self-monitoring` templates routed like the other internal
   alerts (UI, Telegram, push — not SMS, the path that is down):
   `kurier_unreachable` (three failed pings in a row) and `kurier_modem_down`
   (modem not registered or SIM not ready), each with its recovery.
5. Klopot does not `DELETE` its watchdog when it stops: a deliberately stopped
   Klopot should alert, and the 180 s timeout covers the gap of a deploy.

The contract (payload, states, limits) is Kurier ADR-0001; this ADR changes
nothing in it.

## Consequences

- One request a minute gives both directions: Kurier knows Klopot is alive
  and healthy, Klopot knows Kurier and its modem are. An internet outage, a
  dead or stuck Klopot all end in an SMS.
- New code: the provider (config, validation, the send), the ping task and
  its health summary, two templates in the `self-monitoring` pack, the
  channel editor section (en + ro), tests for each; docs in
  `docs/INTEGRATIONS_ROADMAP.md` → a Kurier section, `docs/API.md` (channel
  config), `docs/OPERATIONS.md`.
- Several `kurier` channels with the watchdog on each register their own
  watchdog — documented; one is enough.
- Not covered: the whole host down (Klopot and Kurier die together). That
  needs a watcher outside the host — a separate decision.

## Alternatives

- **Kurier as a module inside Klopot** — Klopot down would take the SMS path
  with it.
- **Kurier polling `/v1/health/ready`** — no Klopot change, but readiness
  does not see a stalled engine, and Kurier would become an active prober.
- **Pinging from the engine loop** — proves the loop runs, but puts network
  latency into rule evaluation (IP-01 again). A separate task that reports the
  engine's tick age proves the same without it.
- **Klopot's MQTT heartbeat** — proves only that one MQTT output connection
  is alive, not the engine; and it needs a broker in the path.
