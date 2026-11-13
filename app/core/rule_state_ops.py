"""Transactional rule-evaluation-state operations shared by the config
surfaces that can change a rule's matching semantics (REST PATCH and config
import).

Audit B-06: editing a rule's condition expression resets the *live* engine
streak (``RuleEngine.reload_rules``), but the persisted ``rule_state`` row is
only rewritten on the next evaluation. A restart in that gap restored a streak
counted against the *old* expression, so one match of the new condition could
satisfy ``persist_n``. The reset must therefore be durable and race-safe:

1. Reset the persisted streak in the SAME transaction as the expression change.
2. Version the persisted state (``Rule.state_epoch`` / ``RuleState.state_epoch``)
   so a stale in-flight runtime that writes its old count back after the reset
   is stamped with the old epoch and ignored on cold start.

This operation is the single place both PATCH and import call, so the two paths
cannot drift.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Rule, RuleState


async def reset_streak_on_reconfig(
    session: AsyncSession,
    rule: Rule,
    *,
    previous_condition_expr: str | None,
) -> bool:
    """Bump the rule's state epoch and zero its persisted streak when the
    condition expression changed, within the caller's transaction.

    ``previous_condition_expr`` is the expression *before* this update (``None``
    for a freshly created rule, which has no prior streak to invalidate). Keyed
    on ``condition_expr`` to mirror exactly what ``RuleEngine.reload_rules``
    resets live, so the live and persisted resets never disagree.

    Returns ``True`` if a reconfiguration reset was applied.
    """
    if previous_condition_expr is None or rule.condition_expr == previous_condition_expr:
        return False

    rule.state_epoch = (rule.state_epoch or 0) + 1
    st = await session.get(RuleState, rule.id)
    if st is not None:
        st.consecutive_match_count = 0
        st.last_match_at = None
        st.last_eval_result = None
        st.state_epoch = rule.state_epoch
    return True
