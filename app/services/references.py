"""Who reads which variable — for "used by" in the admin UI and the
``used`` filter on ``GET /v1/variables``.

A variable is read by a rule (its ``vars_extract``, ``condition_expr`` and
``recovery_expr``) and by computed variables (their ``formula``). Besides
the names an expression evaluates, names passed in quotes to the helpers
that take one — ``var_age("ac.actual_running")``, ``fresh``, ``has`` — count
too (``eval.display_names``): the rule depends on that variable even though
``eval.referenced_names`` deliberately skips string literals.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.eval import display_names
from ..core.parametric import RuleView, instances
from ..db.models import Rule, Variable, VariableSource


def expression_vars(expr: str | None) -> set[str]:
    """Variable names an expression reads, including helper string args."""
    if not expr:
        return set()
    return set(display_names(expr))


def vars_read(vars_extract: list[str] | None, *expressions: str | None) -> set[str]:
    """Variables read through an explicit list plus expressions."""
    names = set(vars_extract or [])
    for expr in expressions:
        names |= expression_vars(expr)
    return names


def rule_vars(rule: Rule) -> set[str]:
    """What the rule reads — every instance of a parametric rule (ADR-0005)."""
    names: set[str] = set()
    for inst in instances(rule.for_each):
        view = RuleView(rule, inst)
        names |= vars_read(view.vars_extract, view.condition_expr, view.recovery_expr)
    return names


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
