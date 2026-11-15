"""The fire-path dedup lookup is a key equality on ``is_test`` (review K14).

``ix_log_dedup`` is ``(type, is_test, context_hash, fired_at)``. The lookup
filtered ``is_test IS false``, which MySQL does not use as a key equality
(the trap already fixed in dedup_claims): the index degraded to a ``type``
prefix, scanned on every fire. It must compare with ``=``.
"""
from __future__ import annotations

import pytest
from sqlalchemy import event

from app.core.dispatcher import FireEnvelope, fire
from app.db.models import Severity, TemplateChannel

pytestmark = pytest.mark.anyio


async def test_the_dedup_lookup_compares_is_test_with_equals(db_engine, db_session, make_template, make_channel):
    tpl = make_template(type="k14", min_repeat_min=0)
    ch = make_channel(name="ui_k14", rate_limit_per_min=1000)
    db_session.add_all([tpl, ch])
    await db_session.flush()
    db_session.add(TemplateChannel(template_id=tpl.id, channel_id=ch.id, enabled=True, severity_min=Severity.info))
    await db_session.commit()

    seen: list[str] = []

    def capture(conn, cursor, statement, params, context, executemany):
        if "context_hash" in statement and statement.lstrip().upper().startswith("SELECT") \
                and "notifications_log" in statement:
            seen.append(" ".join(statement.split()))

    event.listen(db_engine.sync_engine, "before_cursor_execute", capture)
    try:
        await fire(FireEnvelope(type="k14", context={"v": 1}), db_session)
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", capture)
    assert seen, "the dedup lookup did not run"
    for statement in seen:
        assert "is_test IS" not in statement, statement
