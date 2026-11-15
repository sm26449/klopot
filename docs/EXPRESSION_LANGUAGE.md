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

(`true`, `false` and `null` are reserved words — they never name a
variable — but they are not literals; write `True` / `False` / `None`.)
- Lists: `[1, 2, 3]`
- Dicts: `{'k': 'v'}`

### Variables

Any variable in the state cache — limited to the names in the rule's
`vars_extract` when that list is non-empty. Examples:

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
| `avg([a, b, ...])` | `avg([f1, f2, f3])` | mean |
| `int(x)`, `float(x)`, `bool(x)` | type coercion |  |

### String

| Function | Example | Result |
|----------|---------|--------|
| `contains(s, sub)` | `contains(sms_body, 'STATUS')` | bool |
| `startswith(s, p)` | `startswith(topic, 'sensors/')` | bool |
| `endswith(s, p)` | `endswith(topic, '/W')` | bool |
| `len(s)` | `len(error_msg) > 100` | int |
| `lower(s)`, `upper(s)` | normalize | str |
| `regex_match(s, pat)` | `regex_match(phone, '^\\+40')` | bool |

### Time

| Function | Example | Notes |
|----------|---------|-------|
| `now()` | `now() > deadline` | UTC unix timestamp (seconds) |
| `hour_now()` | `hour_now() >= 22` | local hour 0-23 (in `ALERTD_TZ`) |
| `dow_now()` | `dow_now() in [5, 6]` | day-of-week 0=Mon to 6=Sun |
| `in_window(start_h, end_h)` | `in_window(22, 6)` | bool, crosses midnight if end<start |
| `since_seconds(ts)` | `since_seconds(last_change_ts) > 300` | float seconds; `inf` for `None` |
| `var_age(name)` | `var_age('room.temperature') > 60` | seconds since last update of variable; `inf` if it has no value |

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

A **missing input** — a dotted variable with no value in the cache, compared
directly — is not an error: it records `last_eval_error` (`missing input: …`,
`eval_status = no_data` in the API), breaks the streak, and does not count
towards auto-disable.

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
