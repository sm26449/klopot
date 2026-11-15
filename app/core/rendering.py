"""Title + message template rendering.

Two placeholder syntaxes supported (RMS-style and Python-style):

- ``{var}`` — Python-style; works for simple names and dotted paths
  (``{disk.used_pct}``)
- ``%var%`` — RMS-compatible; same semantics

Missing variables render as ``[?var]`` so the operator can spot
which placeholder didn't resolve. They never crash the renderer.

Optional filters via pipe for common transforms: ``round(n)``,
``fixed(n)``, ``div(n)``, ``pct``, ``lower``, ``upper``, ``json``,
``jsonstr`` — e.g. ``{bytes | div(1073741824) | fixed(1)}`` GB. Filters
chain left-to-right. The admin-UI preview (``lib/render.js``) implements
the same set (tests/core/test_rendering.py checks they match). ``{var | json}`` emits a full JSON value
(quoted for strings); ``{var | jsonstr}`` emits JSON-escaped string
content WITHOUT the quotes, for embedding inside a JSON string literal
(webhook body templates, audit A18).
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# Match either {placeholder} or %placeholder% in ONE pattern (alternation), so
# both syntaxes are substituted in a single pass. Inside, the name can include
# dots and any chain of `| filter` segments.
_PLACEHOLDER = re.compile(
    r"\{([^{}]+?)\}"
    r"|%([a-zA-Z_][\w.]*(?:\s*\|\s*[a-zA-Z_]\w*(?:\([^)]*\))?)*)%"
)

# Cap on rendered output size (audit P0-4), enforced while the output is built
# (review K03): a template that repeats a placeholder over a large value must
# not allocate its whole product first.
_MAX_RENDER_LEN = 100_000


def render(template: str | None, ctx: dict[str, Any]) -> str:
    """Render a template string. Never raises."""
    return render_with_missing(template, ctx)[0]


def render_with_missing(template: str | None, ctx: dict[str, Any]) -> tuple[str, list[str]]:
    """Render ``template`` and list the placeholders that did not resolve.

    ONE pass: a context value that happens to contain ``%x%`` or ``{x}`` is
    placed literally and is NEVER re-expanded as a template (audit P0-4).
    Unresolved names (a missing value or a failed filter, shown as ``[?name]``
    / ``[?name|filter]``) are collected here, during substitution — never by
    scanning the output, where a value could pose as one (review K03).
    The output stops at ``_MAX_RENDER_LEN`` characters as soon as it gets there;
    later placeholders are still checked for a missing value (not for filters).
    """
    if not template:
        return "", []
    missing: dict[str, None] = {}
    parts: list[str] = []
    room = _MAX_RENDER_LEN
    pos = 0
    for m in _PLACEHOLDER.finditer(template):
        spec = (m.group(1) if m.group(1) is not None else m.group(2)).strip()
        if room <= 0:
            # Output is full: only note what is absent (filters are not run).
            name = spec.split("|", 1)[0].strip()
            if _lookup(name, ctx) is None:
                missing.setdefault(name, None)
            continue
        value, unresolved = _resolve_spec(spec, ctx)
        if unresolved is not None:
            missing.setdefault(unresolved, None)
        for piece in (template[pos:m.start()], value):
            parts.append(piece[:room])
            room -= len(parts[-1])
        pos = m.end()
    if room > 0:
        parts.append(template[pos:][:room])
    return "".join(parts), list(missing)


def _resolve(spec: str, ctx: dict[str, Any]) -> str:
    """Resolve ``name | filter1 | filter2(args)`` against ctx."""
    return _resolve_spec(spec, ctx)[0]


def _resolve_spec(spec: str, ctx: dict[str, Any]) -> tuple[str, str | None]:
    """The text for ``spec`` and, when it did not resolve, its base name."""
    parts = [p.strip() for p in spec.split("|")]
    name = parts[0]
    filters = parts[1:]

    value = _lookup(name, ctx)
    if value is None:
        return f"[?{name}]", name

    for f in filters:
        try:
            value = _apply_filter(value, f)
        except Exception:
            logger.debug("filter %r failed on %r", f, value, exc_info=True)
            return f"[?{name}|{f}]", name

    if isinstance(value, float):
        # Avoid ``5.0`` when callers expect ``5``
        if value.is_integer():
            return str(int(value)), None
        return f"{value:g}", None
    return str(value), None


def _lookup(name: str, ctx: dict[str, Any]) -> Any:
    """Look up a possibly-dotted name in the context."""
    if name in ctx:
        return ctx[name]
    # Try traversal: 'battery.soc' → ctx['battery']['soc']
    parts = name.split(".")
    if len(parts) == 1:
        return None
    obj: Any = ctx
    for p in parts:
        if isinstance(obj, dict) and p in obj:
            obj = obj[p]
        else:
            return None
    return obj


# ── Filters ────────────────────────────────────────────────────────


def _apply_filter(value: Any, expr: str) -> Any:
    """Apply one pipe filter. Supports ``name`` and ``name(arg)`` forms."""
    m = re.match(r"^([a-zA-Z_]\w*)(?:\((.*)\))?$", expr)
    if not m:
        raise ValueError(f"bad filter: {expr!r}")
    fname = m.group(1)
    arg_str = m.group(2)

    if fname == "round":
        digits = _clamp_digits(int(arg_str)) if arg_str else 0
        return round(float(value), digits)
    if fname == "pct":
        # Number → integer percent
        return f"{round(float(value)):d}"
    if fname == "div":
        if not arg_str:
            raise ValueError("div requires an argument")
        return float(value) / float(arg_str)
    if fname == "lower":
        return str(value).lower()
    if fname == "upper":
        return str(value).upper()
    if fname == "json":
        import json as _json

        return _json.dumps(value, default=str)
    if fname == "jsonstr":
        # JSON-escape the value's string content WITHOUT the surrounding
        # quotes, so it can be embedded inside a JSON string literal in a
        # webhook body_template (audit A18): e.g. {"text": "**{title |
        # jsonstr}**"} stays valid JSON even when the title contains a
        # quote or newline.
        import json as _json

        return _json.dumps(str(value))[1:-1]
    if fname == "fixed":
        # Cap precision: `fixed(5000000)` would format a number into a 5 MB
        # string (audit P0-4). No real message needs more than a few decimals.
        digits = max(0, _clamp_digits(int(arg_str))) if arg_str else 1
        return f"{float(value):.{digits}f}"
    raise ValueError(f"unknown filter: {fname!r}")


# Precision filters (round/fixed) take a digit count straight from the template;
# clamp it so a huge value can't blow up formatting time or output size (P0-4).
_MAX_FILTER_DIGITS = 12


def _clamp_digits(n: int) -> int:
    return max(-_MAX_FILTER_DIGITS, min(_MAX_FILTER_DIGITS, n))
