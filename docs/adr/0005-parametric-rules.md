# ADR-0005 — Parametric rules: one rule, one instance per value

Status: Accepted
Date: 2026-11-18

## Context

The same check is often needed for several devices. Production has 12 rules
`ov_{active,recovered,severe}_f{1..4}_v1`: per inverter the same condition,
`vars_extract` and template (`ov_active_f1` … `ov_active_f4`), differing only
in `f1`…`f4`. A fix has to be made four times, and they drift. Prometheus
solves this with labels, Zabbix with low-level discovery. The rules review
(2026-11-18, stage 4) asked for "for each of f1..f4".

## Decision

1. **`for_each` on a rule**: one parameter and its values,
   `{"n": ["f1", "f2", "f3", "f4"]}`. Parameter name `[a-z][a-z0-9_]*`; at most
   50 values of `[A-Za-z0-9_.-]{1,32}`. One parameter in this version (no
   cartesian product). `null` = an ordinary rule, as every existing one.
2. **`{n}` placeholders** in `condition_expr`, `recovery_expr`, `vars_extract`,
   `template_type` and `resolved_template_type` are replaced per value before
   anything else: `var_age("ov.{n}.state") < 600 AND ov.{n}.state ==
   "Moderate"` with template `ov_active_{n}`. Each expanded expression is
   validated when the rule is saved; the template variable `n` (the
   parameter's name) carries the value into the title and message.
3. **Each value is an instance with its own life**: its own streak, recovery
   streak, run state and history, incident and de-duplication key. The engine
   keys runtimes by `(rule_id, instance)`; an ordinary rule is instance `""`.
4. **Storage (migration `0046`)**: `rules.for_each` (JSON); `rule_state`
   keyed by `(rule_id, instance)` and holding the instance's `run_state`,
   `run_state_since`, `last_true_at`; `rule_transitions.instance`;
   `incidents.rule_instance`. Existing rows get instance `""`. The rule's own
   `run_state` becomes the summary of its instances (the most urgent:
   error > firing > pending > no_data > inactive) so the list and filters
   work unchanged.
5. **Rule-level parts stay rule-level**: enabled, eval interval, persist,
   inhibition (an inhibitor rule is active if any of its instances is),
   `fire_count_lifetime`, `last_fired_at`. An expression error is the same in
   every instance, so the error count and auto-disable stay per rule; a missing
   input stays per instance (`f4` silent → only `f4` is `no_data`).
6. **API and UI**: `GET /v1/rules/{id}/instances` (state per instance);
   `transitions` take `?instance=`; the editor has a *For each* field and shows
   one row per instance; validate and eval-now take an instance (default: the
   first). Config export/import and packs carry `for_each` as a field.
7. Changing `for_each` is a reconfiguration: removed instances close their
   incidents (as a condition edit does, RV-04), new ones start fresh.

## Consequences

- The 12 `ov_*` rules can become 3 (the owner converts them; existing rules are
  untouched). A fix is made once and the instances cannot drift.
- The engine, rule state, incidents and dispatcher gain an instance key: the
  largest change of the rules work. Every path that reads `rule_state` or
  `incidents.active_rule_id` needs a test with two instances.
- Evaluation cost grows with the instances (4 instances = 4 evaluations a tick).
- Templates still exist per instance when `template_type` uses `{n}`; one
  shared template with `{n}` in its text is the simpler setup.

## Alternatives

- **Editor-only "duplicate for each"** — no engine change, but the copies drift
  again after the first edit.
- **Several parameters (cartesian product)** — no production need yet; the
  format leaves room for it.
- **Discovering instances from variable names** (`ov.*.state`) — closer to
  Zabbix LLD, but an instance appearing or vanishing with a collector restart
  would open and close incidents on its own.
