"""Who reads which variable — for "used by" in the admin UI and the
``used`` filter on ``GET /v1/variables``.

A variable is read by a rule (its ``vars_extract``, ``condition_expr`` and
``recovery_expr``) and by computed variables (their ``formula``). Besides
the names an expression evaluates, names passed as string arguments to the
helpers — ``var_age("ac.actual_running")`` — count too: the rule depends on
that variable even though ``eval.referenced_names`` deliberately skips
string literals.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.eval import KEYWORD_WORDS, referenced_names
from ..db.models import Rule, Variable, VariableSource

# helper("some.var") / helper('some_var', …)
_STRING_ARG = re.compile(r"""\b[A-Za-z_]\w*\(\s*["']([A-Za-z_][\w.]*)["']""")


def expression_vars(expr: str | None) -> set[str]:
    """Variable names an expression reads, including helper string args."""
    if not expr:
        return set()
    names = set(referenced_names(expr)) | set(_STRING_ARG.findall(expr))
    return {n for n in names if n.lower() not in KEYWORD_WORDS}


def vars_read(vars_extract: list[str] | None, *expressions: str | None) -> set[str]:
    """Variables read through an explicit list plus expressions."""
    names = set(vars_extract or [])
    for expr in expressions:
        names |= expression_vars(expr)
    return names


def rule_vars(rule: Rule) -> set[str]:
    return vars_read(rule.vars_extract, rule.condition_expr, rule.recovery_expr)


def computed_vars(var: Variable) -> set[str]:
    if var.source != VariableSource.computed:
        return set()
    return expression_vars((var.config or {}).get("formula"))


@dataclass
class Usage:
    rules: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)

    @property
    def used(self) -> bool:
        return bool(self.rules or self.variables)


async def variable_usage(session: AsyncSession) -> dict[str, Usage]:
    """Map variable name → the rules and computed variables that read it.

    Small tables (hundreds of rows), so one pass over each is cheap."""
    usage: dict[str, Usage] = defaultdict(Usage)
    for rule in (await session.execute(select(Rule).order_by(Rule.name))).scalars():
        for name in rule_vars(rule):
            usage[name].rules.append(rule.name)
    computed = (await session.execute(
        select(Variable).where(Variable.source == VariableSource.computed).order_by(Variable.name)
    )).scalars()
    for var in computed:
        for name in computed_vars(var) - {var.name}:
            usage[name].variables.append(var.name)
    return usage
