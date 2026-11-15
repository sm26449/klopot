"""A rule that fires again after going false is never merged away silently (review C13).

A non-incident rule whose context does not change (``door_open: true``) that
went false and true again inside the idempotency window (5 min) was merged
into its previous notification: nothing sent, and no row recorded that it
happened. Decision: such a re-occurrence is logged as a suppressed
``duplicate`` row. A rule that simply stays true keeps coalescing without
a row per evaluation.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.channels.manager import DispatchOutcome
from app.core.engine import RuleEngine
from app.core.state_cache import StateCache
from app.db import get_session_factory
from app.db.models import NotificationLog, Severity, TemplateChannel

pytestmark = pytest.mark.anyio


async def _ok(self, notif, names, session, **_kw):
    return DispatchOutcome(succeeded=list(names), failed={})


async def _rows():
    async with get_session_factory()() as s:
        return (await s.execute(select(NotificationLog).order_by(NotificationLog.fired_at))).scalars().all()


async def _engine(db_session, make_rule, make_template, make_channel):
    tpl = make_template(type="door", severity=Severity.warning, title_template="Door open", min_repeat_min=0)
    ch = make_channel(name="ui_door", rate_limit_per_min=1000)
    rule = make_rule(template_type=tpl.type, condition_expr="door_open", persist_n=1, vars_extract=[])
    db_session.add_all([tpl, ch, rule])
    await db_session.flush()
    db_session.add(TemplateChannel(template_id=tpl.id, channel_id=ch.id, enabled=True, severity_min=Severity.info))
    await db_session.commit()
    engine = RuleEngine()
    engine._cache = StateCache()
    await engine.reload_rules()
    return engine, engine._rules[rule.id]


async def test_a_reoccurrence_inside_the_window_is_logged_as_duplicate(
    db_engine, db_session, make_rule, make_template, make_channel,
):
    engine, rt = await _engine(db_session, make_rule, make_template, make_channel)
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        for value in (True, False, True):
            await engine._cache.set("door_open", value)
            await engine._eval_rule(rt, now=time.monotonic())
    rows = await _rows()
    assert [r.suppressed_reason.value if r.suppressed_reason else None for r in rows] == [None, "duplicate"]


async def test_a_rule_that_stays_true_does_not_log_a_row_per_evaluation(
    db_engine, db_session, make_rule, make_template, make_channel,
):
    engine, rt = await _engine(db_session, make_rule, make_template, make_channel)
    await engine._cache.set("door_open", True)
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        for _ in range(4):
            await engine._eval_rule(rt, now=time.monotonic())
    assert len(await _rows()) == 1
