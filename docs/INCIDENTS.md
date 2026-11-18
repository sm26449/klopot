# Incidents and recovery

An incident represents one problem episode from detection to resolution.
Notifications are delivery events belonging to it. Acknowledgement means a
human has seen the problem; it does not declare it resolved.

## Enable on a rule

In the rule editor, select **Track as an incident**, enter an optional recovery
condition and choose the template used to announce recovery. Example rule fields:

```json
{
  "incident_enabled": true,
  "condition_expr": "temperature > 80",
  "persist_n": 2,
  "recovery_expr": "temperature < 75",
  "recovery_persist_n": 2,
  "resolved_template_type": "temperature_normal"
}
```

Both conditions use the normal expression language and the rule's captured,
fresh variables. These fields also round-trip through config import/export.
Incident tracking defaults to false; existing rules remain unchanged.

Two consecutive readings over 80 open one incident. Repeated fires belong to
it and respect normal routing, inhibition and throttling. A value of 78 leaves
it active. Two consecutive readings below 75 resolve it. A true trigger takes
precedence if the thresholds overlap. Recovery is only evaluated for an open
episode. When `recovery_expr` is null, a successful false trigger evaluation
is a recovery confirmation. `persist_n` and `recovery_persist_n` count engine
evaluations, not elapsed seconds.

Expression errors or missing-input evaluation failures break the confirmation
streak and keep the incident open. Open incidents and recovery counters survive
restart. In the hysteresis band a live incident remains an active inhibitor.

A **parametric rule** (`for_each`, [ADR-0005](adr/0005-parametric-rules.md))
opens one incident per instance: `ov_active_v2[f2]` and `ov_active_v2[f3]` are
separate episodes, each with its own recovery. Changing `for_each` (like
changing the condition) closes the open ones as `rule_reconfigured`. The
rule's `run_state` is `firing` while any instance's incident is open.

## Recovery notifications

Null `resolved_template_type` resolves silently. Otherwise the chosen template
uses its own severity, routing, snoozes, quiet hours and repeat throttle —
and is sent only if the episode was **announced**: a firing notice reached a
channel (or is being sent at that moment), or someone acknowledged the
incident. A failure nobody heard of (snoozed, in quiet hours, throttled,
failed on every channel, or still queued when it cleared — that queued page is
cancelled) closes without a recovery notice: "back to normal" would be news
about nothing. The incident row still records the resolution.
Retention never deletes the notifications of an episode that is still open,
so an episode that stays open longer than the notification retention period
still announces its end.
A separate info template is usually appropriate. Its context contains current
values plus `_incident.id`, `_incident.rule_name`, `_incident.event` (`resolved`),
`_incident.opened_at` (UTC), and `_incident.duration_sec`. Firing notifications
have the same metadata without duration and with event `firing`.

The state transition and notification outbox intent commit together before
any transport. A restart cannot lose the recovery notice after resolution has
committed. If routing/gating suppresses the notice, its log records the reason.
Recovery delivery does not increment the rule's alarm counter.

Resolution cancels queued firing deliveries and escalation. A send already in
flight may finish. Claimed deliveries are skipped during cancellation; the
worker checks resolution again before retrying them. A fully cancelled fire
has `delivery_status=cancelled`. Successful delivery facts remain intact.

## Operating incidents

The **Incidents** page defaults to active episodes and supports state, ack and
text filters, detail snapshots, rule links and related notification history.
Refresh updates episode state and duration; delivery details are in the related
notification log. No historical telemetry replay is implied. The log links back
to the incident.

Ack on an incident or any associated notification covers the whole episode,
including future repeats, and stops escalation. Repeating ack preserves the
first actor/time. It leaves ordinary firing delivery and the active state alone.

Manual resolution requires a reason and leaves acknowledgement independent.
It does not send a telemetry-recovery notice. If the trigger persists, a fresh
episode opens after new confirmations; use snooze to silence a known problem.

Changing the trigger or incident configuration closes the previous episode
with reason `rule_reconfigured`, without declaring recovery. Dry-run import
rolls this administrative closure back with all other changes. Disabling or
deleting a rule leaves active incidents for manual review; deleted rules keep
their names in history. Active incidents are retained. Resolved incidents are
pruned after log retention only when no retained notification references them,
including pending recovery deliveries.

## External episodes

The same incident model carries episodes that do not come from a rule
(`source_kind` other than `rule`, migration `0028`):

| `source_kind` | Opened by | Identity (`source_key`) |
|---------------|-----------|--------------------------|
| `fire` | `POST /v1/fire` with an `idempotency_key` | `fire:<api key name>:<idempotency_key>` |
| `alertmanager` | an Alertmanager / Grafana input | `am:<input id>:<fingerprint>` |

All go through the shared fire service (`app/core/fire_service.py`):

- The first firing opens the episode and notifies; repeats while it is open
  notify nothing (escalation still runs until someone acknowledges).
- An episode nobody was told about is the exception: while no firing notice
  has gone out (the first was snoozed, in quiet hours, throttled, or failed
  on every channel), each repeat goes through the gates again, and the
  alert is announced by the first repeat that nothing mutes. This needs the
  source to repeat (Alertmanager does, every `repeat_interval`); Klopot does
  not announce it by itself when the snooze or the quiet hours end. An
  episode acknowledged meanwhile is not announced (someone has it), and two
  repeats arriving at once announce it once.
- A resolution from the source closes it with reason `recovered`, cancels
  pending escalation and sends `resolved_template_type` if set and the
  episode was announced (see Recovery notifications). It is not an
  acknowledgement.
- A firing with a newer source start time (Alertmanager `startsAt`) closes the
  previous episode as `superseded` and opens a new one; a resolution for an
  older start is ignored, so a late message cannot close a newer episode.
- `active_source_key` is unique while the episode is open and cleared on
  resolution, so concurrent first firings (two Alertmanager replicas) open
  exactly one episode — the loser of the race is answered as a repeat.

The detail drawer shows the source instead of a rule link. Ack, manual
resolution and retention work as for rule incidents. Provider message ids are
recorded per delivery (`deliveries.provider_ref`, e.g. ntfy, Gotify).

## Pushover emergencies

A Pushover channel can send chosen severities as **emergency** (repeat until
someone acknowledges). The two acknowledgements stay in sync, each applied
once (`app/core/provider_lifecycle.py`, migration `0029`):

- Acknowledging in Klopot (UI, API, Telegram, an incident) queues a durable
  `cancel_receipt` command per open receipt; the provider-lifecycle worker
  runs it with backoff, so the phone stops ringing even if Pushover was
  briefly unreachable.
- Acknowledging in the Pushover app is picked up by polling the receipt
  (~every 60 s, works behind NAT): Klopot records an inbound event and
  acknowledges the alert with actor `pushover:<device>` — which also stops
  escalation. Expired receipts are recorded and no longer polled.
