"""Parametric rules (ADR-0005): one rule, one instance per value.

A rule with ``for_each = {"n": ["f1", "f2"]}`` is evaluated once per value;
``{n}`` in its condition, recovery, ``vars_extract`` and template types is
replaced by the value. :class:`RuleView` is the rule as one instance sees it:
the expanded fields, everything else read from (and written to) the rule.
An ordinary rule is the single instance ``""``.
"""
from __future__ import annotations

import re
from typing import Any

PARAM = re.compile(r"^[a-z][a-z0-9_]*$")
VALUE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
MAX_VALUES = 50
EXPANDED = ("condition_expr", "recovery_expr", "template_type", "resolved_template_type")


def normalize_for_each(raw: Any) -> dict[str, list[str]] | None:
    """The stored form, or ValueError with the reason. ``None`` / ``{}`` =
    an ordinary rule."""
    if raw is None or raw == {}:
        return None
    if not isinstance(raw, dict) or len(raw) != 1:
        raise ValueError('for_each takes one parameter and its values: {"n": ["f1", "f2"]}')
    (param, values), = raw.items()
    if not isinstance(param, str) or not PARAM.match(param):
        raise ValueError(f"for_each: parameter name must match [a-z][a-z0-9_]*, got {param!r}")
    if not isinstance(values, list) or not values:
        raise ValueError("for_each: the values must be a non-empty list")
    if len(values) > MAX_VALUES:
        raise ValueError(f"for_each: at most {MAX_VALUES} values")
    out: list[str] = []
    for v in values:
        if not isinstance(v, str) or not VALUE.match(v):
            raise ValueError(f"for_each: a value must match [A-Za-z0-9_.-]{{1,32}}, got {v!r}")
        if v in out:
            raise ValueError(f"for_each: {v!r} is listed twice")
        out.append(v)
    return {param: out}


def instances(for_each: dict[str, list[str]] | None) -> list[str]:
    """The instance keys: the values, or ``[""]`` for an ordinary rule."""
    if not for_each:
        return [""]
    return list(next(iter(for_each.values())))


def param_of(for_each: dict[str, list[str]] | None) -> str | None:
    return next(iter(for_each)) if for_each else None


def expand(text: str | None, for_each: dict[str, list[str]] | None, instance: str) -> str | None:
    """``text`` with ``{param}`` replaced by the instance's value."""
    param = param_of(for_each)
    if text is None or param is None:
        return text
    return text.replace("{" + param + "}", instance)


def expanded_fields(rule: Any, instance: str) -> dict[str, Any]:
    """The instance's condition, recovery, template types and vars_extract."""
    fe = rule.for_each
    out: dict[str, Any] = {f: expand(getattr(rule, f), fe, instance) for f in EXPANDED}
    out["vars_extract"] = [expand(v, fe, instance) for v in (rule.vars_extract or [])]
    return out


def check_expressions(for_each: dict[str, list[str]] | None, validate: Any, *exprs: str | None) -> None:
    """Run ``validate`` on every expression as every instance sees it; the
    error names the instance. Raises what ``validate`` raises."""
    for inst in instances(for_each):
        for expr in exprs:
            if not expr:
                continue
            try:
                validate(expand(expr, for_each, inst))
            except Exception as e:
                if inst:
                    raise type(e)(f"[{inst}] {e}") from e
                raise


class RuleView:
    """One instance of a rule. Expanded fields are fixed at construction;
    every other attribute reads and writes the wrapped rule (so the engine's
    ``rt.rule.enabled = False`` still disables the rule)."""

    __slots__ = ("_fields", "_rule", "instance")

    def __init__(self, rule: Any, instance: str = "") -> None:
        object.__setattr__(self, "_rule", rule)
        object.__setattr__(self, "instance", instance)
        object.__setattr__(self, "_fields", expanded_fields(rule, instance) if instance else {})

    def __getattr__(self, name: str) -> Any:
        fields = object.__getattribute__(self, "_fields")
        if name in fields:
            return fields[name]
        return getattr(object.__getattribute__(self, "_rule"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_rule"), name, value)

    @property
    def raw(self) -> Any:
        return object.__getattribute__(self, "_rule")

    @property
    def binding(self) -> dict[str, str]:
        """``{"n": "f1"}`` for the template context; ``{}`` for a plain rule."""
        param = param_of(self.raw.for_each)
        return {param: self.instance} if param and self.instance else {}

    @property
    def display_name(self) -> str:
        return f"{self.raw.name}[{self.instance}]" if self.instance else self.raw.name
