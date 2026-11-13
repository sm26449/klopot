# Expression language for rule conditions

Rule conditions are short Python-like expressions evaluated against
the live state cache. The expressions must be:

- **Safe** — no arbitrary code execution, no imports, no attribute
  walking
- **Predictable** — every operator and function whitelisted; nothing
  surprising
- **Bounded** — 100 ms timeout per evaluation
- **Testable** — pure inputs → pure output, no I/O during eval

We use **simpleeval** as the foundation, with a custom whitelist of
names and functions specific to alerting use cases.

---

## Supported syntax

### Operators

```
Arithmetic:    + - * / % **
Comparison:    < <= > >= == !=
Boolean:       AND OR NOT  (also: && || !)
Membership:    in   not in
Ternary:       a if cond else b
Grouping:      ( ... )
Subscript:     x[0]   d['key']
String concat: 'a' + 'b'
```

### Literals

- Numbers: `42`, `3.14`, `1_000_000`
- Strings: `'hello'`, `"world"`
- Booleans: `True`, `False`, `true`, `false`
- None: `None`, `null`
- Lists: `[1, 2, 3]`
- Dicts: `{'k': 'v'}`

### Variables

Any name declared in `vars_extract` of the rule (mapped to the state
cache). Examples:

```
consumption.house_load_w
battery.soc
pv.total_w
ratio  # if computed via formula
```

Dot-notation in variable names works because we expose them as keys
in a `dict`, and the parser supports key lookup. Internally:
`consumption.house_load_w` is one key, not a chain of attribute
accesses (which simpleeval blocks for safety).

---

## Built-in functions

These are always available in any expression:

### Numeric

| Function | Example | Result |
|----------|---------|--------|
| `abs(x)` | `abs(-5)` | `5` |
| `min(a, b, ...)` | `min(pv, 45000)` | smaller |
| `max(a, b, ...)` | `max(soc, 15)` | larger |
| `round(x, n=0)` | `round(3.14159, 2)` | `3.14` |
| `clamp(x, lo, hi)` | `clamp(soc, 0, 100)` | bounded |
| `sum([a, b, ...])` | `sum([f1, f2, f3])` | sum |
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
| `hour_now()` | `hour_now() between 22 and 6` | local hour 0-23 (in `settings.timezone`) |
| `dow_now()` | `dow_now() in [5, 6]` | day-of-week 0=Mon to 6=Sun |
| `in_window(start_h, end_h)` | `in_window(22, 6)` | bool, crosses midnight if end<start |
| `since_seconds(ts)` | `since_seconds(last_change_ts) > 300` | int |
| `var_age(name)` | `var_age('pv.total_w') > 60` | seconds since last update of variable |

### Aggregation (over short history)

The engine keeps a short ring-buffer per variable (last 60 samples
by default). Helpful for "X minutes of consistent behavior" rules.

| Function | Example | Notes |
|----------|---------|-------|
| `recent_avg(name, sec)` | `recent_avg('pv.total_w', 300) > 40000` | avg over last N sec |
| `recent_max(name, sec)` | `recent_max('battery.temp', 600) > 50` | max over last N sec |
| `recent_min(name, sec)` | `recent_min('battery.soc', 3600) < 20` | min over last N sec |
| `is_rising(name, sec)` | `is_rising('battery.temp', 600)` | trend detection |

---

## Realistic examples

### Simple threshold

```
battery.soc < 15
```

### Compound

```
battery.soc < 15 AND pv.total_w < 500
```

### With computed ratio

Variable definition (in DB):
```yaml
- name: consumption.ratio_now
  source: computed
  formula: "consumption.house_load_w / consumption.expected_w_now"
```

Rule condition:
```
consumption.house_load_w > 2000 AND consumption.ratio_now > 2.0
```

### Time-windowed

```
battery.temp > 45 AND in_window(7, 19)
```
(High battery temp during daylight hours only.)

### SMS keyword

```
contains(upper(sms_inbox.body), 'STATUS')
AND sms_inbox.from in approved_phones
```

### Sustained behavior (alternative to persist_n)

```
recent_avg('pv.total_w', 300) > 40000
```
(PV averaged > 40 kW over the last 5 minutes — stronger than
persist_n which counts samples.)

### Trend

```
is_rising('battery.temp', 600) AND battery.temp > 40
```
(Temperature is rising AND already warm.)

---

## What's NOT supported (intentionally)

| Forbidden | Reason | Workaround |
|-----------|--------|------------|
| `__import__`, `__class__`, `__builtins__` | RCE risk | n/a — never needed for alerting |
| Comprehensions (`[x for x in ...]`) | Pathological eval (memory) | Use the agg functions |
| Lambda definitions | Can hide arbitrary code | Use the variable-formula mechanism |
| Loops, function defs | n/a in expressions | Out of scope for a rule predicate |
| `getattr`, `setattr`, `hasattr` | Bypass the whitelist | Vars are dict keys |
| Arbitrary attribute access (`x.something.other.thing`) | Object walking | Variables can have dots in their names — they're keys |

If you need behavior that doesn't fit the language, the right path is
to add a **computed variable** that does the work in pure Python (you
control the formula, but it goes through the same simpleeval) — or
extend the function whitelist with a new built-in. See
[`EXTENSIBILITY.md`](EXTENSIBILITY.md) for adding functions.

---

## Error handling

If a rule's expression raises (undefined var, type error, timeout):

1. The exception is caught
2. `rule_state.last_eval_error` is set with the message
3. The rule is **counted as not matched** for this tick
4. After 5 consecutive errors, the rule is **auto-disabled**
   (`rules.enabled = false`) and a built-in alert
   `rule_eval_error` fires (severity warning, dispatched to admin)
5. Admin can re-enable after fixing the expression

This mirrors how good monitoring systems treat sensor errors:
silent on transient noise, loud on persistent breakage.
