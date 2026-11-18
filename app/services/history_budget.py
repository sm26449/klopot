"""Write-time check of the history budget (ADR-0004, rc.9 review RC-03).

The history tracks the variables the enabled rules (every instance) and
computed formulas read through ``avg_over`` & co., at most
``ALERTD_HISTORY_MAX_VARS``. A write that would need more is refused here,
before commit — never by silently dropping another rule's history.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.history import get_history_store, merge_needs
from ..core.parametric import RuleView, instances
from ..db.models import Rule, Variable, VariableSource


async def history_budget_problem(session: AsyncSession) -> str | None:
    """Why the configuration in ``session`` (flushed, not committed) needs more
    history than allowed, or None."""
    await session.flush()
    rules = (await session.execute(select(Rule).where(Rule.enabled.is_(True)))).scalars().all()
    rule_needs = merge_needs(
        e for r in rules for inst in instances(r.for_each)
        for e in (RuleView(r, inst).condition_expr, RuleView(r, inst).recovery_expr))
    computed = (await session.execute(select(Variable).where(
        Variable.enabled.is_(True), Variable.source == VariableSource.computed))).scalars().all()
    computed_needs = merge_needs((v.config or {}).get("formula") for v in computed)
    store = get_history_store()
    total = store.merged_needs(rules=rule_needs, computed=computed_needs)
    if len(total) <= store.max_vars:
        return None
    new = sorted(n for n in total if n not in store.tracked())
    return (f"the history functions would need {len(total)} variables, ALERTD_HISTORY_MAX_VARS is "
            f"{store.max_vars}" + (f" (new: {', '.join(new[:5])}{'…' if len(new) > 5 else ''})" if new else ""))
