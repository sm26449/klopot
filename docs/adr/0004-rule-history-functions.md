# ADR-0004 — History functions in rule expressions

Status: Accepted
Date: 2026-11-18

## Context

The state cache keeps only the latest value of each variable, so a rule can
say "above 80 now" but not "above 80 on average over 5 minutes", "dropped by
more than 10 in an hour", "rising faster than 2 per minute" or "has not changed
for 10 minutes". `persist_n` (and the editor's duration, RL-30) covers only
"true at every check for N checks". Prometheus, Grafana and Zabbix all have
range functions; the rules review (2026-11-18, stage 4) listed them as the
largest functional gap.

Most of our producers publish **on change** (the Fronius and Seplos collectors
use change detection): a value that holds steady sends nothing. An average of
the received samples would over-weight the busy minutes; the right meaning is
the value as a step function over time.

## Decision

1. **Functions**, each taking a variable name and a window as **string
   literals** (`"30s"`, `"5m"`, `"2h"`, at most `24h`):
   `avg_over(name, w)` (time-weighted), `min_over`, `max_over`,
   `delta(name, w)` (now minus the value at the window's start),
   `rate(name, w)` (`delta` per second), `changed(name, w)` (the value changed
   inside the window) and `prev(name)` (the value before the current one).
   Literals only, so every need is known when a rule is saved; anything else is
   refused at write time (`422`), like an unknown function.
2. **Kept in memory, derived from the rules.** On every engine reload the
   history store collects the `(name, window)` pairs used by enabled rules
   (condition and recovery) and computed formulas, and tracks exactly those
   variables for their longest window. Nothing to configure, no migration.
   A variable no rule needs is not tracked.
3. **Bounded.** A tracked variable keeps at most 2 000 buckets over its
   longest window (bucket = window / 2 000, e.g. 0.15 s for 5 m, 43 s for
   24 h); each bucket keeps first, last, min, max and the time-weighted area,
   so min/max stay exact and the average is exact to the bucket. At most
   `ALERTD_HISTORY_MAX_VARS` (default 200) tracked variables: a rule that would
   exceed it is refused when saved.
4. **Missing data stays missing.** Until the history covers the whole window
   (after a start, or a variable seen for the first time) the function is a
   missing input: the rule is `no_data` with "history: 2m of 5m". A variable
   that is stale now is missing too. Non-numeric values make the numeric
   functions a missing input; `changed` and `prev` take any value.
5. **One store, every evaluator**: the engine, eval-now, validate and computed
   variables read the same store (through `settings_evaluator`). Validate of a
   rule not saved yet says the variable is not tracked until it is saved.
6. A metric `alertd_history_tracked_vars` and the store's size in
   `/v1/health` details.

## Consequences

- Rules like `avg_over("battery.temp", "10m") > 45` or
  `delta("battery.soc", "1h") < -30` need no new variables or collectors.
- After every restart, a rule using a 24 h window is `no_data` for 24 h. That
  is the price of keeping it in memory (owner's choice, 2026-11-18); a later
  ADR can add a periodic snapshot if it hurts.
- Memory: at the defaults, a few MB at most (200 × 2 000 small tuples).
- The engine reload must rebuild the tracked set; a new rule starts with an
  empty history for a variable nobody tracked before.
- `scripts/rules_sim.sh` gets scenarios for each function; the expression
  cheat-sheet and completion list them.

## Alternatives

- **Snapshot to the database** so history survives a restart — more writes
  and a migration; deferred.
- **Opt-in per variable** (`history_sec` on the variable) — explicit, but one
  more setting to keep in step with the rules that need it.
- **Average of samples** instead of time-weighted — wrong for on-change data.
- **Query InfluxDB** — not every install has it, and a rule tick must not wait
  on an external query.
