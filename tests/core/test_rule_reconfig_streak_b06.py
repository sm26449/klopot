"""B-06: editing a rule's condition expression must durably reset its match
streak, so a restart cannot restore a streak counted against the old
expression.

The live engine already zeroes the counter on an in-process reload when the
expression changed, but the persisted ``rule_state`` row was only rewritten on
the next evaluation. A restart in that gap (``RuleEngine.reload_rules`` cold
start) restored the old count, so a single match of the *new* condition could
satisfy a ``persist_n`` that was never met for it.

The fix resets the persisted streak in the same transaction as the expression
change (shared by REST PATCH and config import) and versions the persisted
state with ``state_epoch`` so a stale in-flight runtime cannot write the old
count back afterward.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.engine import RuleEngine
from app.core.rule_state_ops import reset_streak_on_reconfig
from app.db.models import Rule, RuleState
from app.services import config_io

pytestmark = pytest.mark.anyio


async def _seed_with_streak(
    db_session, make_rule, make_template, *, expr="x > 10", count=2, epoch=0,
):
    """A persist-3 rule mid-ramp: ``count`` consecutive matches persisted."""
    t = make_template(type="r_type", min_repeat_min=0)
    r = make_rule(template_type="r_type", condition_expr=expr,
                  vars_extract=["x"], persist_n=3, eval_interval_sec=30)
    db_session.add_all([t, r])
    await db_session.commit()
    await db_session.refresh(r)
    db_session.add(RuleState(
        rule_id=r.id, consecutive_match_count=count, state_epoch=epoch,
    ))
    await db_session.commit()
    return r


async def _cold_start_count(db_engine, rule_id: int) -> int:
    """A fresh engine with an empty runtime map takes the cold-start path,
    exactly like a process restart."""
    engine = RuleEngine()
    await engine.reload_rules()
    return engine._rules[rule_id].consecutive_match_count


async def test_reconfig_bumps_epoch_and_zeroes_persisted_streak(
    db_engine, db_session, make_rule, make_template
):
    """The core fix: changing the expression through the shared helper bumps
    the rule epoch and zeroes the persisted row in the same transaction, so a
    cold start restores zero rather than the old streak."""
    r = await _seed_with_streak(db_session, make_rule, make_template)

    r.condition_expr = "x > 50"  # operator edits the expression
    applied = await reset_streak_on_reconfig(
        db_session, r, previous_condition_expr="x > 10"
    )
    assert applied is True
    assert r.state_epoch == 1
    await db_session.commit()

    st = (await db_session.execute(
        select(RuleState).where(RuleState.rule_id == r.id)
    )).scalar_one()
    assert st.consecutive_match_count == 0
    assert st.state_epoch == 1

    assert await _cold_start_count(db_engine, r.id) == 0


async def test_cold_start_discards_streak_from_an_older_epoch(
    db_engine, db_session, make_rule, make_template
):
    """The epoch gate on its own: even if a persisted row still carries a
    non-zero count (e.g. a stale write landed), cold start ignores it when its
    epoch predates the rule's. Negative control: give the row the current epoch
    and the same count is trusted."""
    r = await _seed_with_streak(db_session, make_rule, make_template, count=2, epoch=0)
    # Expression already moved on one generation; the row is from epoch 0.
    r.state_epoch = 1
    await db_session.commit()
    assert await _cold_start_count(db_engine, r.id) == 0

    # Negative control: a row at the current epoch IS honored.
    st = (await db_session.execute(
        select(RuleState).where(RuleState.rule_id == r.id)
    )).scalar_one()
    st.state_epoch = 1
    await db_session.commit()
    assert await _cold_start_count(db_engine, r.id) == 2


async def test_stale_runtime_writeback_cannot_resurrect_streak(
    db_engine, db_session, make_rule, make_template
):
    """The race: a tick captured a runtime at the old epoch; after the reset
    commits, that runtime persists its old count. Because it stamps the old
    epoch, cold start still discards it."""
    r = await _seed_with_streak(db_session, make_rule, make_template, count=2, epoch=0)

    # A runtime captured before the reconfig (old epoch, old count).
    engine = RuleEngine()
    await engine.reload_rules()
    rt_old = engine._rules[r.id]
    assert rt_old.state_epoch == 0
    assert rt_old.consecutive_match_count == 2

    # Operator reconfigures: bump epoch + zero the persisted row, committed.
    r.condition_expr = "x > 50"
    await reset_streak_on_reconfig(db_session, r, previous_condition_expr="x > 10")
    await db_session.commit()

    # The stale runtime now flushes its old streak back to the DB.
    await engine._persist_state(rt_old)

    # Its write stamped the OLD epoch, so a restart ignores it.
    assert await _cold_start_count(db_engine, r.id) == 0


async def test_unchanged_expression_preserves_streak(
    db_engine, db_session, make_rule, make_template
):
    """An unrelated edit (same expression) must NOT reset the streak — the
    whole point of persisting ramp-up progress across edits (audit H-1)."""
    r = await _seed_with_streak(db_session, make_rule, make_template, count=2)

    r.sort_order = 7  # edit something that is not the expression
    applied = await reset_streak_on_reconfig(
        db_session, r, previous_condition_expr="x > 10"
    )
    assert applied is False
    assert r.state_epoch == 0
    await db_session.commit()

    assert await _cold_start_count(db_engine, r.id) == 2


async def test_patch_endpoint_resets_streak_on_expression_change(
    db_engine, db_session, db_client, admin_key, make_rule, make_template
):
    """Wiring through the REST surface: PATCH that changes the expression
    zeroes the persisted streak and bumps the epoch; PATCH of an unrelated
    field leaves the streak intact."""
    r = await _seed_with_streak(db_session, make_rule, make_template, count=2)
    h = {"X-API-Key": admin_key}

    # Unrelated field: streak preserved.
    resp = await db_client.patch(f"/v1/rules/{r.id}", json={"sort_order": 3}, headers=h)
    assert resp.status_code == 200
    st = (await db_session.execute(
        select(RuleState).where(RuleState.rule_id == r.id)
    )).scalar_one()
    await db_session.refresh(st)
    assert st.consecutive_match_count == 2
    assert st.state_epoch == 0

    # Expression change: streak reset, epoch bumped.
    resp = await db_client.patch(
        f"/v1/rules/{r.id}", json={"condition_expr": "x > 99"}, headers=h
    )
    assert resp.status_code == 200
    # End this session's transaction so the next read starts a fresh snapshot —
    # under MySQL REPEATABLE READ the assertion session would otherwise keep the
    # pre-PATCH view and not see the API request's committed reset.
    await db_session.rollback()
    await db_session.refresh(st)
    assert st.consecutive_match_count == 0
    assert st.state_epoch == 1


async def test_config_import_resets_streak_on_expression_change(
    db_engine, db_session, make_rule, make_template
):
    """Wiring through config import: an import that rewrites a rule's
    expression resets its persisted streak the same way PATCH does."""
    r = await _seed_with_streak(db_session, make_rule, make_template, count=2)

    pack = {"rules": [{
        "name": r.name, "template_type": "r_type", "condition_expr": "x > 99",
        "persist_n": 3, "vars_extract": ["x"],
    }]}
    plan = await config_io.import_config(db_session, pack, apply=True)
    assert plan.ok, plan.errors
    await db_session.commit()

    st = (await db_session.execute(
        select(RuleState).where(RuleState.rule_id == r.id)
    )).scalar_one()
    assert st.consecutive_match_count == 0
    assert st.state_epoch == 1

    # And the rule really did take the new expression.
    r2 = (await db_session.execute(select(Rule).where(Rule.id == r.id))).scalar_one()
    assert r2.condition_expr == "x > 99"
