"""NaN / Infinity never reach a JSON column or a JSON response (audit P06).

``json.loads`` accepts the ``NaN`` / ``Infinity`` literals that Python, C and
many firmware publishers emit; JSON has no such values and MySQL rejects a
document containing one. A ``json`` variable carrying one made every fire
that included it fail, each cycle, with only a log line.
"""
from __future__ import annotations

import json
import math
import time

import pytest
from sqlalchemy import select

from app.core.dispatcher import FireEnvelope, _envelope_hash, _json_safe, fire
from app.core.engine import RuleEngine
from app.core.state_cache import StateCache
from app.core.variable_resolver import _coerce
from app.db import get_session_factory
from app.db.models import NotificationLog, Severity, TemplateChannel


def test_json_safe_replaces_non_finite_numbers():
    got = _json_safe({"a": float("nan"), "b": [1.5, float("inf"), {"c": float("-inf")}], "d": "NaN", "e": 2})
    assert got == {"a": None, "b": [1.5, None, {"c": None}], "d": "NaN", "e": 2}
    json.dumps(got, allow_nan=False)   # what MySQL and JSONResponse require


def test_a_json_variable_is_cleaned_when_it_is_read():
    got = _coerce(json.loads('{"t": NaN, "ok": true, "hist": [1, Infinity], "n": 3.5}'), "json")
    assert got == {"t": None, "ok": True, "hist": [1, None], "n": 3.5}
    assert _coerce(float("nan"), "number") is None
    assert math.isfinite(_coerce("3.5", "number"))


def test_dedup_hash_matches_the_stored_payload():
    """The hash is taken over what is stored, so NaN and null are one context."""
    a = FireEnvelope(type="t", context={"x": float("nan")})
    b = FireEnvelope(type="t", context={"x": None})
    assert _envelope_hash(a) == _envelope_hash(b)


async def test_a_fire_with_nan_in_its_context_is_stored(db_session, make_template, make_channel):
    tpl = make_template(type="nan_ctx", min_repeat_min=0)
    ch = make_channel(name="ui_nan", rate_limit_per_min=1000)
    db_session.add_all([tpl, ch])
    await db_session.flush()
    db_session.add(TemplateChannel(template_id=tpl.id, channel_id=ch.id, enabled=True, severity_min=Severity.info))
    await db_session.commit()
    r = await fire(FireEnvelope(type="nan_ctx", context={"reading": {"t": float("nan")}, "v": float("inf")}), db_session)
    await db_session.commit()
    row = (await db_session.execute(select(NotificationLog).where(NotificationLog.id == r.id))).scalar_one()
    assert row.vars_payload == {"reading": {"t": None}, "v": None}


@pytest.mark.mysql
async def test_rule_still_fires_when_an_unrelated_json_variable_holds_nan(
    db_session, make_rule, make_template, make_channel,
):
    """The engine gives a rule with an empty ``vars_extract`` every variable."""
    tpl = make_template(type="overheat", severity=Severity.critical, title_template="hot {x}")
    ch = make_channel(name="ui_x", rate_limit_per_min=1000)
    rule = make_rule(template_type=tpl.type, condition_expr="x > 80", persist_n=1, vars_extract=[])
    db_session.add_all([tpl, ch, rule])
    await db_session.flush()
    db_session.add(TemplateChannel(template_id=tpl.id, channel_id=ch.id, enabled=True, severity_min=Severity.info))
    await db_session.commit()
    engine = RuleEngine()
    engine._cache = StateCache()
    await engine.reload_rules()
    await engine._cache.set("x", 95.0)
    # Straight into the cache, as a value that slipped past the input would be.
    await engine._cache.set("weather_station", json.loads('{"t": NaN, "ok": true}'))

    await engine._eval_rule(engine._rules[rule.id], now=time.monotonic())

    async with get_session_factory()() as s:
        logs = (await s.execute(select(NotificationLog))).scalars().all()
    assert logs, "x=95 > 80 matched, but no notification was stored"
