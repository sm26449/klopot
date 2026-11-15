# Edge cases & semantics

This document describes how alertd behaves in scenarios that are
easy to get wrong. Each section answers a single question precisely.

---

## Stale variables

**Q.** A variable hasn't been updated in 60 seconds. What happens
when a rule evaluates a condition that uses it?

**A.** Each variable has a `stale_after_sec` in its config (default
300 s for `mqtt` / `aggregate` / `computed`; `constant` and `schedule`
variables never go stale — `app/core/staleness.py`). A value is stale
when its age exceeds that window (or, for an aggregate / computed value,
when the evidence it was derived from expires).

When the engine builds a rule's context it **drops stale variables**. The
expression then sees them as missing (see the next section): a dotted name
is bound to `None`, so `var_age('x') < 60 and x > 5` simply evaluates
false, while a direct comparison against the `None` is recorded as a
*missing input* (`eval_status = no_data`), breaks the persist streak and
does not fire. Nothing is written to `notifications_log`.

A rule that wants to reason about age explicitly uses `var_age("name")`,
which reads the cache directly (`inf` when there is no value).

This prevents the classic "the sensor died, but alertd kept firing
`temperature_high` because the last value it ever sent was 41 °C"
failure mode.

---

## Missing variables

**Q.** A rule's `condition_expr` references a variable that doesn't
exist (typo, deleted variable, never published).

**A.** Two cases:

- **A dotted name** (`room.temprature`) with no value is bound to `None`.
  If the expression compares it, the evaluation is a *missing input*:
  `rules.last_eval_error` reads `missing input: room.temprature (…)`, the
  API reports `eval_status = no_data`, the persist streak breaks, and it
  does **not** count towards auto-disable — the rule waits for the input.
- **A plain name** that is not defined, or any other failure (type error,
  rejected syntax), is an evaluation error: `rules.consecutive_eval_errors`
  is incremented, `last_eval_error` is set, and a warning is logged at 5
  in a row.

The rule does NOT fire for that tick. After
`ALERTD_EVAL_ERROR_DISABLE_THRESHOLD` (default 50) consecutive errors the
rule is auto-disabled (`enabled = false`) and the built-in
`rule_auto_disabled` alert fires (template from the `self-monitoring`
pack), so the operator finds out.

If the variable later starts existing (e.g., a typo was fixed), an
auto-disabled rule must be re-enabled by hand; a missing-input rule
recovers on its own once the value arrives.

---

## Retained MQTT messages on subscribe

**Q.** When alertd subscribes to its MQTT topics, it receives the
retained messages on them first.
Do those trigger rule fires?

**A.** No, not directly. Retained messages populate the state
cache **before the engine starts ticking**. The engine's first
tick evaluates rules against the seeded cache; if a rule's
condition is true on that first tick, the persist counter is at
1 (not at `persist_n`), so the rule does NOT fire on tick 1
unless `persist_n=1`.

Practical effect: a retained "server room is hot" topic that hasn't
been republished in 10 minutes does not cause a flood of
`room_temp_high` fires when alertd starts.

Edge case: if `persist_n=1` AND a retained message reflects a
condition that would normally trigger, the rule **will** fire on
startup. This is correct behavior — the operator wants to know
the system is in that state right now.

---

## Out-of-order MQTT messages

**Q.** Two messages on the same topic arrive close together; the
broker delivers them in reverse order due to QoS retransmit. Does
alertd evaluate against the older value?

**A.** No reordering protection is possible from the broker side:
MQTT messages carry no timestamp, so the cache stamps each write with the
loop's monotonic clock and keeps the last value **received**. It drops a
write only if its timestamp is older than the stored one, which protects
against double-callback bugs, not against a broker delivering in the
wrong order.

In practice: this matters for variables published at >5 Hz from
multiple senders. For typical telemetry (most variables update
every 1-10 sec from a single source), out-of-order is rare.

---

## Variable types & coercion

**Q.** A topic publishes `"5.4"` (string) but the variable
declares `type: number`. What does the rule see?

**A.** At extraction time (in the input adapter), the value is
coerced to the declared type:

| Declared | Input | Result |
|----------|-------|--------|
| `number` | `"5.4"` | `5.4` (float) |
| `number` | `true` | `1.0` |
| `number` | `"abc"`, NaN, ±inf | `None` (the variable holds no usable value) |
| `bool` | `"true"`, `"1"`, `"yes"`, `"on"` (any case) | `True` |
| `bool` | any other string | `False` |
| `bool` | non-string | `bool(value)` |
| `string` | anything | `str(value)` |
| `json` | anything | passed through; a NaN or ±inf anywhere inside becomes `null` (not JSON: MySQL and API responses reject them) |

A JSON `null` at the path is stored as `None` (it invalidates the previous
value); a path that does not resolve skips the update. There is no built-in
alert on coercion failures.

---

## Timezone for hour_now() / in_window() / quiet_hours

**Q.** What timezone do time-based functions use?

**A.** All time-based eval uses the **service-level timezone**
from `ALERTD_TZ` (default `UTC`), NOT the operator's browser TZ.
(Compose also sets the container's `TZ` from it.)

This is intentional: an alert evaluated in two different operator
sessions must produce identical outcomes. Quiet hours `"22-07"`
means 22:00–07:00 in `ALERTD_TZ` regardless of who is
asking.

DST transitions (e.g. EET ↔ EEST in Europe/Bucharest):

- "Spring forward" (lose an hour at 03:00): if a schedule fires
  at 03:30 on that night, it fires once at the equivalent local
  time after the jump. If quiet_hours is "22-07", the window is
  22:00–07:00 wall-clock; the missing hour 03:00–04:00 simply
  doesn't exist.
- "Fall back" (gain an hour at 04:00): a schedule firing at 03:30
  on that night fires ONCE (we use the first occurrence
  semantically). Quiet hours that span the doubled hour treat
  both occurrences as in-window.

Implementation uses `zoneinfo` (stdlib in Python 3.9+) with the
TZ database that ships with the python:3.12-slim image.

---

## Persist N + Throttle interaction

**Q.** A rule has `persist_n=20` (must match 20 consecutive ticks)
and the template has `min_repeat_min=60` (cooldown). I want to
understand exactly when fires happen.

**A.** Sequential gates:

1. **Eval** — rule's `condition_expr` returns truthy.
2. **Persist counter** — `consecutive_match_count` is incremented.
   If counter ≥ `persist_n`, proceed; else stop (but counter is
   saved). On a non-match, counter resets to 0.
3. **Throttle gate (in dispatcher)** — if `last_fired_at >
   now - min_repeat_min`, mark suppressed `throttled` and write
   the row but do NOT dispatch.
4. **Other gates** — snoozed, delivery gate, quiet_hours.
5. **Dispatch** — write log row + send to channels.

Concretely: after the first fire, the counter resets to 0. The
template throttle starts. Even if the condition stays true and
the persist counter rebuilds to 20 in 10 minutes, the dispatcher
suppresses the second fire because we're still in the
`min_repeat_min=60` cooldown. The log row is written with
`suppressed_reason='throttled'` so the operator sees the
suppressed attempt.

---

## Idempotency vs Throttle

**Q.** Both look like deduplication. What's the difference?

| | Idempotency | Throttle |
|---|------------|----------|
| **Scope** | (type, hash(vars)) | (type) |
| **Window** | 5 min (configurable) | template's `min_repeat_min` |
| **Trigger** | Same caller fires the same payload twice | Different events with same type |
| **Result** | The fire is deduplicated onto the existing row, NO new row written | New log row written, `suppressed_reason='throttled'` |
| **Counter** | None | Updates `last_fired_at` only on dispatched fire |

Idempotency protects against retries (Node-RED retries because of network
flake → same `{type, vars}` arrives twice within seconds). Throttle
protects against operator noise (rule keeps matching → don't fire
hourly).

A duplicate is coalesced onto a first fire that was delivered (`sent`,
`partial`) **or is still being delivered** (`pending`, retries running): it
is the same alert, and it shares that outcome — if every retry of the first
fails, the duplicate is not sent on its own. An identical fire *after* the
first has failed for good is admitted and delivered afresh.

A rule (without incidents) that went false and true again inside the window
with the same values is a new occurrence: it is not sent twice either, but it
is logged as a suppressed row with reason `duplicate`, so the log and the
digest show it. A rule that simply stays true adds no such rows.

Both can apply to the same fire. Idempotency runs first; if a
recent dup exists, return early. Otherwise, gating runs and
throttle applies.

---

## Snooze + Ack interaction

**Q.** I `ack` a notification. Does that snooze further fires of
the same type?

**A.** No. `ack` is a per-row action — it sets
`notifications_log.acknowledged_at` for that one entry. Future
fires of the same type are unaffected.

To stop further fires, use snooze:

- `POST /v1/snooze` — scope can be `type` / `rule` / `channel`,
  until any timestamp. (The admin UI and the Telegram *Snooze* button
  create the same rows.)

Snooze auto-expires at `until`. The first fire after expiry is
NOT itself snoozed.

---

## Snooze precedence

**Q.** A type is snoozed at scope `type`, but I have a `rule`-scope
snooze on a different rule of the same type. What wins?

**A.** Any matching snooze wins (deny). Snoozes are OR-ed together:
the dispatcher denies if ANY snooze matches the (type, rule,
channel) tuple.

So: snoozing type `disk_full` denies all rules that fire it.
Snoozing rule_id=42 denies only that rule, even if other rules
also fire `disk_full`. Snoozing channel_id=7 denies routes
to channel 7 but allows other channels.

A "channel snooze" doesn't block the fire — the log row is still
written and channels other than the snoozed one still dispatch; the
snoozed channel is simply left out (it does not appear in
`failed_channels`). If every routed channel is snoozed, the fire is
suppressed with reason `snoozed`.

---

## Webhook input replay

**Q.** A webhook input receives a duplicate POST (network retry).
Does the rule fire twice?

**A.** Each webhook payload is treated as a fresh value. If the
caller sends the same body twice, the variable is updated twice
(same value). Rule evaluation runs the same way in both cases —
counter increments either way.

There is no inbound `Idempotency-Key` for webhook inputs. Deduplication
happens downstream: a rule needs `persist_n` consecutive matches, the
template's cooldown applies, and an identical fire within the idempotency
window (`ALERTD_IDEMPOTENCY_WINDOW_SEC`, 5 min) is not written twice. A
caller that fires directly can send `idempotency_key` to `POST /v1/fire`.

---

## Channel partial failure

**Q.** A fire routes to UI, Telegram, and SMS. UI succeeds, Telegram
times out, SMS succeeds. What does the log show?

**A.**
```json
{
  "id": "ntf_...",
  "dispatched_to": ["ui", "sms"],
  "failed_channels": {"telegram": "timeout after 5s"},
  "suppressed_reason": null,
  "delivery_status": "partial",
  "dispatch_latency_ms": 4200
}
```

`delivery_status` is `partial` (≥1 channel succeeded, ≥1 failed) once
Telegram's delivery has failed terminally; `pending` while it is still
being retried, `sent` if the retry succeeds. The fire is
NOT considered suppressed — operators got the notification on UI
and SMS. Telegram failure is recorded for diagnosis but doesn't
escalate to a "missed alert" classification.

If ALL channels fail, `delivery_status = failed`, `failed_channels`
contains all of them, but `suppressed_reason` is still null
(suppression is a deliberate gate, not a transport failure). There is
no built-in "all channels failed" alert: failed deliveries show on the
Operations page, in `/v1/operations` and in the queue metrics
([OPERATIONS.md](OPERATIONS.md)). Note that each failed channel is
first retried by the delivery worker (5 attempts) before it counts as
failed.

---

## Bootstrap admin key

**Q.** First time alertd starts, how do I make the first
admin API call?

**A.** Set `ALERTD_BOOTSTRAP_ADMIN_KEY` to a plaintext key
(generate with `python -c "import secrets;
print('alertd_'+secrets.token_urlsafe(32))"`). On first run,
alertd checks if `api_keys` is empty; if so, it inserts a
single key with `name='bootstrap'`, `scopes=['admin']`, and
the bcrypt-hash of the env var.

After first run, the env var is no longer consulted. To rotate,
use `POST /v1/api_keys/{id}/rotate`.

If you lost the bootstrap key, sign in to the admin UI as `admin` and
create a new key (API keys page); a lost admin password is reset with
`docker compose exec alertd python -m scripts.admin --username admin
reset-password` (see [DEPLOY.md](DEPLOY.md#first-login)). Direct SQL is
not needed.

---

## Multiple API keys for one caller

**Q.** Can the same caller (e.g., Node-RED) have multiple API keys
active simultaneously?

**A.** Yes. They authenticate independently. Useful during
rotation: issue new key, deploy Node-RED with the new key, revoke old key.
Both work during the overlap.

The `name` column is unique, so each key has its own name. By
convention: `<service>-<purpose>` like `node-red-fire`,
`node-red-admin`.

---

## Time-bounded API keys

**Q.** Can I issue a temporary key for a contractor?

**A.** Yes. Set `expires_at` on creation. After the timestamp,
the key returns 401. The expired row stays in the table for
audit; admin can manually delete it later.
