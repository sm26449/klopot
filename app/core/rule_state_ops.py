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

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Rule, RuleState
from .incidents import active_incident, lifecycle_config, resolve


async def reset_streak_on_reconfig(
    session: AsyncSession,
    rule: Rule,
    *,
    previous_condition_expr: str | None,
    previous_lifecycle: tuple[Any, ...] | None = None,
) -> bool:
    """Bump the rule's state epoch and zero its persisted streak when the
    condition expression changed, within the caller's transaction.

    ``previous_condition_expr`` is the expression *before* this update (``None``
    for a freshly created rule, which has no prior streak to invalidate). Keyed
    on ``condition_expr`` to mirror exactly what ``RuleEngine.reload_rules``
    resets live, so the live and persisted resets never disagree.

    Returns ``True`` if a reconfiguration reset was applied.
    """
    lifecycle_changed = (
        previous_lifecycle is not None
        and bool(previous_lifecycle[0] or rule.incident_enabled)
        and previous_lifecycle != lifecycle_config(rule)
    )
    if previous_condition_expr is None or (
        rule.condition_expr == previous_condition_expr and not lifecycle_changed
    ):
        return False

    rule.state_epoch = (rule.state_epoch or 0) + 1
    # The run state described the old condition: clear it durably, so a
    # restart before the first evaluation does not load it as current
    # (2026-11-18 rc.6 verification, RV-04). ``run_state_since`` stays as
    # the marker: a NULL state with a since = "changed, not evaluated yet".
    if rule.run_state is not None:
        rule.run_state = None
    st = await session.get(RuleState, rule.id)
    if st is not None:
        st.consecutive_match_count = 0
        st.recovery_match_count = 0
        st.last_match_at = None
        st.last_eval_result = None
        st.state_epoch = rule.state_epoch
    incident = await active_incident(session, rule.id)
    if incident is not None:
        # A config edit does not prove that the original problem recovered.
        await resolve(session, incident, {}, reason="rule_reconfigured")
    return True
