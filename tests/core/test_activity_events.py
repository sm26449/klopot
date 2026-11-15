"""System events (docs/ACTIVITY_LOG.md): written on state changes only."""
from __future__ import annotations

from sqlalchemy import select

from app.core.activity import get_activity_writer
from app.core.engine import RuleEngine
from app.core.manager import InputManager
from app.core.state_cache import StateCache
from app.db.models import SystemEvent


class _FakeInput:
    def __init__(self, connected, error=None):
        self.connected, self.error = connected, error

    def health(self):
        return {"connected": self.connected, "error": self.error}


async def _events(db_session):
    await get_activity_writer().flush()
    return [(e.source_kind, e.source_name, e.event) for e in
            (await db_session.execute(select(SystemEvent).order_by(SystemEvent.id))).scalars()]


async def test_input_transitions_only(db_session):
    mgr = InputManager()
    broker = _FakeInput(True)
    mgr._adapters = {"broker": broker}
    mgr._note_input_transitions()          # healthy at first sight → nothing
    mgr._note_input_transitions()          # unchanged → nothing
    broker.connected, broker.error = False, "Connection refused"
    mgr._note_input_transitions()
    mgr._note_input_transitions()          # still down → nothing new
    broker.connected, broker.error = True, None
    mgr._note_input_transitions()
    assert await _events(db_session) == [("input", "broker", "error"), ("input", "broker", "recovered")]


async def test_rule_error_and_recovery_are_events_once(db_engine, db_session, make_rule, make_template):
    engine = RuleEngine()
    engine._cache = StateCache()
    t = make_template(type="r_type")
    r = make_rule(template_type="r_type", condition_expr="x > 10", vars_extract=["x"], persist_n=1)
    db_session.add_all([t, r])
    await db_session.commit()
    await engine.reload_rules()
    rt = engine._rules[r.id]
    for _ in range(3):
        rt.consecutive_eval_errors += 1
        await engine._record_eval_error(rt, "NameError: x")
    rt.consecutive_eval_errors = 0
    await engine._record_eval_error(rt, None)
    assert [e[2] for e in await _events(db_session)] == ["eval_error", "eval_recovered"]


async def test_missing_input_gap_is_not_an_event(db_engine, db_session, make_rule, make_template):
    """A restart leaves every rule without data for a tick: no error/recovered pair."""
    engine = RuleEngine()
    engine._cache = StateCache()
    t = make_template(type="g_type")
    r = make_rule(template_type="g_type", condition_expr="y > 1", vars_extract=["y"], persist_n=1)
    db_session.add_all([t, r])
    await db_session.commit()
    await engine.reload_rules()
    rt = engine._rules[r.id]
    await engine._record_eval_error(rt, "missing input: y", real=False)
    await engine._record_eval_error(rt, None)
    assert await _events(db_session) == []
    rt.consecutive_eval_errors = 1                         # a real error after a gap
    await engine._record_eval_error(rt, "NameError: y")
    await engine.reload_rules()                            # the open event survives a reload
    rt = engine._rules[r.id]
    rt.consecutive_eval_errors = 0
    await engine._record_eval_error(rt, None)
    from tests._db import fresh
    await fresh(db_session)                                # MySQL: new snapshot before re-reading
    assert [e[2] for e in await _events(db_session)] == ["eval_error", "eval_recovered"]
