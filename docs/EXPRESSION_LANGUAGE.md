# Expression language for rule conditions

Rule conditions are short Python-like expressions evaluated against
the live state cache. The expressions must be:

- **Safe** — no arbitrary code execution, no imports, no attribute
  walking
- **Predictable** — every operator and function whitelisted; nothing
  surprising
- **Bounded** — size limits instead of a timer: at most 2000 characters,
  500 syntax nodes and 40 levels of nesting; `**`, `*` and `%` results are
  capped at run time (no huge integers or strings)
- **Testable** — pure inputs → pure output, no I/O during eval

We use **simpleeval** as the foundation, with a custom whitelist of
names and functions specific to alerting use cases.

---

## Supported syntax

### Operators

```
Arithmetic:    + - * / % **
Comparison:    < <= > >= == !=
Boolean:       AND OR NOT  (also lowercase: and or not)
Membership:    in   not in
Ternary:       a if cond else b
Grouping:      ( ... )
Subscript:     x[0]   d['key']
String concat: 'a' + 'b'
```

### Literals

- Numbers: `42`, `3.14`, `1_000_000`
- Strings: `'hello'`, `"world"` (not triple-quoted; an expression may not
  contain control characters other than tab and newline)
- Booleans: `True`, `False`
- None: `None`

`true` / `false` / `null` / `none` — lowercase, uppercase or capitalised —
are literals too (the same as `True` / `False` / `None`); they never name a
variable.
- Lists: `[1, 2, 3]`
- Dicts: `{'k': 'v'}`

### Variables

Any variable in the state cache. When the rule's `vars_extract` is
non-empty, the rule sees the names listed there **plus every variable its
condition and recovery expressions read** — a variable used in the
expression is never left out. Examples:

```
disk.used_pct
room.temperature
api.latency_ms
ratio  # if computed via formula
```

Dot-notation in variable names works because we expose them as keys
in a `dict`, and the parser supports key lookup. Internally:
`disk.used_pct` is one key, not a chain of attribute accesses (which
simpleeval blocks for safety).

---

## Built-in functions

These are always available in any expression:

### Numeric

| Function | Example | Result |
|----------|---------|--------|
| `abs(x)` | `abs(-5)` | `5` |
| `min(a, b, ...)` | `min(latency, 5000)` | smaller |
| `max(a, b, ...)` | `max(level, 15)` | larger |
| `round(x, n=0)` | `round(3.14159, 2)` | `3.14` (`n` between -100 and 100) |
| `clamp(x, lo, hi)` | `clamp(level, 0, 100)` | bounded |
| `sum([a, b, ...], start=0)` | `sum([f1, f2, f3])` | sum (numbers only) |
| `avg([a, b, ...])` | `avg([f1, f2, f3])` | mean of the values that are not `None`; with none left the rule waits for data (an empty literal list is an error) |
| `int(x)`, `float(x)`, `bool(x)` | type coercion |  |
| `between(x, lo, hi)` | `between(battery.soc, 20, 80)` | `lo <= x <= hi`; a missing `x` waits for data |
| `coalesce(a, b, ...)` | `coalesce(battery.soc, 50) < 20` | the first value that is not `None` — a default for an input that may be missing |

### Lists

| Function | Example | Result |
|----------|---------|--------|
| `any([a, b, ...])` | `any([pv.f1_status == 7, pv.f2_status == 7])` | true if any element is true (instead of a long `OR` chain) |
| `all([a, b, ...])` | `all([pv.f1_seen_ok, pv.f2_seen_ok])` | true if every element is true; `all([])` is true |

### String

| Function | Example | Result |
|----------|---------|--------|
| `contains(s, sub)` | `contains(sms_body, 'STATUS')` | bool |
| `startswith(s, p)` | `startswith(topic, 'sensors/')` | bool |
| `endswith(s, p)` | `endswith(topic, '/W')` | bool |
| `len(s)` | `len(error_msg) > 100` | int |
| `lower(s)`, `upper(s)` | normalize | str |
| `regex_match(s, pat)` | `regex_match(phone, '^\\+40')` | bool — [RE2 syntax](https://github.com/google/re2/wiki/Syntax): no lookahead / lookbehind / backreferences. A pattern RE2 cannot run is refused when the rule is saved and is an evaluation error at run time (never a silent `False`); so is a subject over 4096 characters |

### Time

| Function | Example | Notes |
|----------|---------|-------|
| `now()` | `now() > deadline` | UTC unix timestamp (seconds) |
| `hour_now()` | `hour_now() >= 22` | local hour 0-23 (in `ALERTD_TZ`) |
| `dow_now()` | `dow_now() in [5, 6]` | day-of-week 0=Mon to 6=Sun |
| `is_weekend()` | `is_weekend()` | Saturday or Sunday (local) |
| `month_now()` | `month_now() in [11, 12, 1]` | local month 1-12 |
| `in_window(start, end)` | `in_window(22, 6)`, `in_window("22:30", "06:15")` | local time in `[start, end)`; each bound an hour (`8`, `7.5`) or `"HH:MM"`; crosses midnight if end < start |
| `since_seconds(ts)` | `since_seconds(last_change_ts) > 300` | float seconds; `inf` for `None` |

### Sun

Needs the place of the install: `ALERTD_LATITUDE` and `ALERTD_LONGITUDE`
(degrees, north / east positive). Without them these functions are an
evaluation error. The position is computed locally (NOAA formulas, within a
fraction of a degree: sunrise and sunset within a couple of minutes).

| Function | Example | Notes |
|----------|---------|-------|
| `is_daylight()` | `is_daylight() AND pv.total_w < 50` | the sun is above the horizon (between standard sunrise and sunset) — instead of a fixed `in_window(8, 20)` |
| `sun_elevation()` | `sun_elevation() > 15` | degrees above the horizon, negative at night |

### Data age

A variable name is passed **in quotes** to these functions.

| Function | Example | Notes |
|----------|---------|-------|
| `var_age(name)` | `var_age('room.temperature') > 60` | seconds since last update of variable; `inf` if it has no value |
| `fresh(name, sec)` | `fresh("battery.soc", 900) AND battery.soc < 20` | `var_age(name) < sec` — the data is recent enough to judge |
| `has(name)` | `has("grid.voltage")` | the variable holds a value that is not stale |

A call to any other function name is refused when the rule is saved.

### Not available

There are no history functions (`recent_avg`, `recent_max`, `recent_min`,
`is_rising`): the state cache keeps only the latest value of each variable.
For "sustained" behaviour use the rule's `persist_n` (consecutive matching
evaluations).

---

## Realistic examples

### Simple threshold

```
disk.used_pct > 90
```

### Compound

```
disk.used_pct > 90 AND disk.free_gb < 20
```

### With computed ratio

Variable definition (in DB):
```yaml
- name: api.error_ratio
  source: computed
  formula: "api.errors_per_min / api.requests_per_min"
```

Rule condition:
```
api.requests_per_min > 100 AND api.error_ratio > 0.05
```

### Time-windowed

```
room.temperature > 28 AND in_window(9, 18)
```
(Server room too warm during office hours only.)

### Daytime, any of several inverters

```
is_daylight() AND fresh("pv.f1_status", 120)
AND any([pv.f1_status == 7, pv.f2_status == 7, pv.f3_status == 7, pv.f4_status == 7])
```

### SMS keyword

```
contains(upper(sms_inbox.body), 'STATUS')
AND sms_inbox.from in approved_phones
```

---

## What's NOT supported (intentionally)

| Forbidden | Reason | Workaround |
|-----------|--------|------------|
| `__import__`, `__class__`, `__builtins__` | RCE risk | n/a — never needed for alerting |
| Comprehensions (`[x for x in ...]`) | Pathological eval (memory) | `sum([...])`, `avg([...])`, `min` / `max` |
| Lambda definitions | Can hide arbitrary code | Use the variable-formula mechanism |
| Loops, function defs | n/a in expressions | Out of scope for a rule predicate |
| `getattr`, `setattr`, `hasattr` | Bypass the whitelist | Vars are dict keys |
| Attribute / method access (`x.upper()`), slices, set literals, keyword arguments, `*args` | Object walking / unbounded work | Variables can have dots in their names — they're keys; use `upper(x)` |

If you need behavior that doesn't fit the language, the right path is
to add a **computed variable** that does the work in pure Python (you
control the formula, but it goes through the same simpleeval) — or
extend the function whitelist with a new built-in (`make_evaluator` in
`app/core/eval.py`).

---

## Error handling

If a rule's expression raises (undefined var, type error, rejected syntax):

1. The exception is caught
2. `rules.last_eval_error` is set with the message and
   `rules.consecutive_eval_errors` is incremented
3. The rule is **counted as not matched** for this tick (the persist
   streak is broken)
4. A warning is logged at 5 consecutive errors; at
   `ALERTD_EVAL_ERROR_DISABLE_THRESHOLD` (default 50, `0` = never) the rule
   is **auto-disabled** (`rules.enabled = false`) and the built-in
   `rule_auto_disabled` alert fires (template from the `self-monitoring` pack)
5. Admin can re-enable after fixing the expression

A **missing input** — a variable (dotted or not) with no value in the cache,
or one whose value is `None`, used where a value is needed (a comparison,
`NOT x`, `lower(x)`, `avg` of nothing) — is not an error: it records
`last_eval_error` (`missing input: …`, `eval_status = no_data` in the API),
breaks the streak, and does not count towards auto-disable. A misspelt
variable therefore shows as `no_data`; the editor's **Validate** lists it as
unknown. An unknown *function* is an error.

This mirrors how good monitoring systems treat sensor errors:
silent on transient noise, loud on persistent breakage.

---

## Template placeholders and filters

Titles and messages of a template (and the webhook / SMS `body_template`)
are filled from the firing context: `{name}` or `%name%`, dotted paths
(`{disk.used_pct}`). A name that does not resolve renders as `[?name]`
and the editor preview lists it. Filters transform a value and chain
left to right:

| Filter | Example | Result |
|--------|---------|--------|
| `round(n)` | `{x \| round(1)}` with 3.456 | `3.5` |
| `fixed(n)` | `{x \| fixed(2)}` with 3.4 | `3.40` (default 1 decimal) |
| `div(n)` | `{bytes \| div(1073741824) \| fixed(1)}` | gigabytes, 1 decimal |
| `pct` | `{ratio_pct \| pct}` with 84.6 | `85` |
| `lower`, `upper` | `{severity \| upper}` | `WARNING` |
| `json` | `{value \| json}` | a JSON value, strings quoted |
| `jsonstr` | `{"text": "{title \| jsonstr}"}` | escaped text for inside a JSON string |

The admin-UI preview implements exactly the same filters as the server.
