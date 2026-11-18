# ADR-0004 — History functions in rule expressions

Status: Accepted
Date: 2026-11-18
Amended: 2026-11-18 — exact change points instead of merged buckets (the buckets gave wrong max / mean / changed for a short window on a long-tracked variable); the budget is enforced when saving, a tracked variable is never evicted; the history follows the state cache's invalidations; `/v1/health` carries no store detail (the metric does); memory measured (rc.9 review RC-02 … RC-05)

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
3. **Exact, bounded.** *(Amended.)* A tracked variable keeps its exact change
   points (time, value; an unchanged value is no new point) over its longest
   window, at most 10 000 of them: every answer is exact — the average from the
   step function, min / max / changed from the points. Past 10 000 changes the
   oldest go, and a window they no longer cover is a missing input ("the last
   10 000 changes are kept"), never an approximation. At most
   `ALERTD_HISTORY_MAX_VARS` (default 200) tracked variables: a rule, computed
   formula, bulk enable or import that would need more is refused when saved
   (`422` / an import error); a variable already tracked is never pushed out by
   a new need.
4. **Missing data stays missing.** Until the history covers the whole window
   (after a start, or a variable seen for the first time) the function is a
   missing input: the rule is `no_data` with "history: 2m of 5m". A variable
   that is stale now, or that the state cache dropped (an input reconfigured —
   its history is started over), is missing too. Non-numeric values make the numeric
   functions a missing input; `changed` and `prev` take any value.
5. **One store, every evaluator**: the engine, eval-now, validate and computed
   variables read the same store (through `settings_evaluator`). Validate of a
   rule not saved yet says the variable is not tracked until it is saved.
6. A metric `alertd_history_tracked_vars`. *(Amended: no `/v1/health` detail.)*

## Consequences

- Rules like `avg_over("battery.temp", "10m") > 45` or
  `delta("battery.soc", "1h") < -30` need no new variables or collectors.
- After every restart, a rule using a 24 h window is `no_data` for 24 h. That
  is the price of keeping it in memory (owner's choice, 2026-11-18); a later
  ADR can add a periodic snapshot if it hurts.
- Memory *(amended)*: about 40 bytes per change point (a float in an array
  plus the value object), so at most ≈ 0.4 MB per variable at the 10 000-point
  cap and ≈ 80 MB if all 200 tracked variables were saturated; a variable that
  changes rarely costs almost nothing. The rc.9 audit measured 65 MB of Python
  allocations for 200 saturated bucket series. Raise the variable limit only
  with that in mind.
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
