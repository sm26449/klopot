# Edge cases & semantics

This document describes how alertd behaves in scenarios that are
easy to get wrong. Each section answers a single question precisely.

---

## Stale variables

**Q.** A variable hasn't been updated in 60 seconds. What happens
when a rule evaluates a condition that uses it?

**A.** Each variable has an optional `stale_after_sec` in its
config. The engine tags the variable as stale when:
`now - var._ts > stale_after_sec`.

When a rule's expression references a stale variable, the engine
evaluates the expression with the *last known value*, but the rule
output is **suppressed** with reason `gated` (specifically
`gated:stale_input`). The fire is recorded in `notifications_log`
with `suppressed_reason = 'gated'` and `error_detail = {"stale":
["pv.total_w"]}` so operators can see why.

Exception: variables explicitly marked `tolerate_stale: true` in
their config are evaluated as-is even when stale (rare; for
intentionally slow variables like `pv_avg_7d`).

This prevents the classic "PV sensor died at noon, but alertd kept
firing `pv_record_70kw` because the last value was 67 kW" failure
mode.

---

## Missing variables

**Q.** A rule's `condition_expr` references a variable that doesn't
exist (typo, deleted variable, never published).

**A.** The expression eval returns an exception (NameError-like).
The engine catches it, increments `rules.consecutive_eval_errors`,
and logs:

```
WARNING rule[N]: eval error: name 'consumption.house_loa_w' is not defined
```

The rule does NOT fire for this tick. After 5 consecutive errors,
the rule is auto-disabled (`enabled = false`) and an internal
`rule_eval_error` alert fires to admin channels (so the operator
finds out).

If the variable later starts existing (e.g., a typo was fixed),
the operator must manually `enabled = true` the rule.

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

Practical effect: a retained "battery is hot" topic that hasn't
been republished in 10 minutes does not cause a flood of
`battery_temp_high` fires when alertd starts.

Edge case: if `persist_n=1` AND a retained message reflects a
condition that would normally trigger, the rule **will** fire on
startup. This is correct behavior — the operator wants to know
the system is in that state right now.

---

## Out-of-order MQTT messages

**Q.** Two messages on the same topic arrive close together; the
broker delivers them in reverse order due to QoS retransmit. Does
alertd evaluate against the older value?

**A.** Each variable update carries the broker's delivery
timestamp. The state cache stores `{value, ts, source}` and only
overwrites the value if the new `ts >= current ts` (monotonic
guarantee). Out-of-order messages are silently discarded.

In practice: this matters for variables published at >5 Hz from
multiple senders. For typical telemetry (most variables update
every 1-10 sec from a single source), out-of-order is rare.

---

## Variable types & coercion

**Q.** A topic publishes `"5.4"` (string) but the variable
declares `type: number`. What does the rule see?

**A.** At extraction time (in the input adapter), the value is
coerced to the declared type:

| Declared | String input | Result |
|----------|--------------|--------|
| `number` | `"5.4"` | `5.4` (float) |
| `number` | `"abc"` | extraction fails, value not stored, log warning |
| `bool` | `"true"`, `"1"`, `1`, `True` | `True` |
| `bool` | `"false"`, `"0"`, `0`, `False`, `null` | `False` |
| `string` | anything | `str(value)` |
| `json` | `'{"k":"v"}'` | parsed `dict` |

Failed coercions don't fire the rule and are logged at WARNING
level. Repeated coercion failures (≥10 in 1 minute on the same
variable) trigger an internal `variable_coercion_errors` alert.

---

## Timezone for hour_now() / in_window() / quiet_hours

**Q.** What timezone do time-based functions use?

**A.** All time-based eval uses the **service-level timezone**
from `settings.timezone` (default `UTC`), NOT the
container's TZ env var, NOT the operator's browser TZ.

This is intentional: an alert evaluated in two different operator
sessions must produce identical outcomes. Quiet hours `"22-07"`
means 22:00–07:00 in `settings.timezone` regardless of who is
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
4. **Other gates** — snoozed, quiet_hours.
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
| **Result** | Returns existing log row, NO new row written | New log row written, `suppressed_reason='throttled'` |
| **Counter** | None | Updates `last_fired_at` only on dispatched fire |

Idempotency protects against retries (NR retries because of network
flake → same `{type, vars}` arrives twice within seconds). Throttle
protects against operator noise (rule keeps matching → don't fire
hourly).

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

- `POST /v1/log/{id}/snooze` — convenience endpoint that snoozes
  the type of that log entry until a default duration (1 hour).
- `POST /v1/snooze` — explicit, scope can be `type` / `rule` /
  `channel`, until any timestamp.

Snooze auto-expires at `until`. The first fire after expiry is
NOT itself snoozed.

---

## Snooze precedence

**Q.** A type is snoozed at scope `type`, but I have a `rule`-scope
snooze on a different rule of the same type. What wins?

**A.** Any matching snooze wins (deny). Snoozes are OR-ed together:
the dispatcher denies if ANY snooze matches the (type, rule,
channel) tuple.

So: snoozing type `consumption_high` denies all rules that fire it.
Snoozing rule_id=42 denies only that rule, even if other rules
also fire `consumption_high`. Snoozing channel_id=7 denies routes
to channel 7 but allows other channels.

A "channel snooze" doesn't block the fire — the log row is still
written, channels other than the snoozed one still dispatch. The
snoozed channel's name appears in `failed_channels` with reason
`channel_snoozed`.

---

## Webhook input replay

**Q.** A webhook input receives a duplicate POST (network retry).
Does the rule fire twice?

**A.** Each webhook payload is treated as a fresh value. If the
caller sends the same body twice, the variable is updated twice
(same value). Rule evaluation runs the same way in both cases —
counter increments either way.

To deduplicate, the webhook caller can include an
`Idempotency-Key` header on inbound webhooks. alertd remembers
keys for 5 min and returns 200 on dup without firing the input
update.

This is the same semantics as `POST /v1/fire`'s
`Idempotency-Key`.

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
  "dispatch_latency_ms": 4200
}
```

`dispatched = true` if at least one channel succeeded. The fire is
NOT considered suppressed — operators got the notification on UI
and SMS. Telegram failure is recorded for diagnosis but doesn't
escalate to a "missed alert" classification.

If ALL channels fail, `dispatched = false`, `failed_channels`
contains all of them, but `suppressed_reason` is still null
(suppression is a deliberate gate, not a transport failure). A
transport failure that affects all channels triggers an internal
`all_channels_failed` alert.

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

If you forgot the bootstrap key and lost access, the recovery
path is direct DB:

```sql
UPDATE api_keys SET enabled = FALSE WHERE id = 1;
INSERT INTO api_keys (name, key_hash, key_prefix, scopes)
VALUES ('emergency', '<bcrypt of new key>', '<first 8 chars>', '["admin"]');
```

(Worth scripting; punted to S12 hardening.)

---

## Multiple API keys for one caller

**Q.** Can the same caller (e.g., NR) have multiple API keys
active simultaneously?

**A.** Yes. They authenticate independently. Useful during
rotation: issue new key, deploy NR with new key, revoke old key.
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
