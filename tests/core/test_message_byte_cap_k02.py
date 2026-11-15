"""A rendered message always fits ``notifications_log.message`` (review K02).

The column is ``TEXT``: 65,535 bytes on MySQL. The renderer caps its output at
100,000 *characters*, so a long context value (a log excerpt, an Alertmanager
description; 32 K Romanian diacritics are already 64 KiB) made strict MySQL
refuse the row (error 1406) and the alert was lost — on every retry.
SQLite does not enforce the length, hence the unit test on the helper plus a
MySQL test of the whole fire.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.dispatcher import MESSAGE_MAX_BYTES, FireEnvelope, fire, fit_message
from app.db.models import NotificationLog, Severity, TemplateChannel

pytestmark = pytest.mark.anyio


def test_fit_message_cuts_on_a_character_boundary():
    assert fit_message("short") == "short"
    exact = "a" * MESSAGE_MAX_BYTES
    assert fit_message(exact) == exact
    for unit in ("a", "ș", "🔥"):            # 1, 2 and 4 bytes in UTF-8
        cut = fit_message(unit * 70_000)
        data = cut.encode("utf-8")           # would raise on a split character
        assert len(data) <= MESSAGE_MAX_BYTES
        assert cut.endswith("…")
        assert len(data) > MESSAGE_MAX_BYTES - 8


async def _seed(db_session, make_template, make_channel, type_: str):
    tpl = make_template(type=type_, min_repeat_min=0, message_template="{log}")
    ch = make_channel(name=f"ui_{type_}", rate_limit_per_min=1000)
    db_session.add_all([tpl, ch])
    await db_session.flush()
    db_session.add(TemplateChannel(template_id=tpl.id, channel_id=ch.id, enabled=True, severity_min=Severity.info))
    await db_session.commit()


async def test_a_long_message_is_stored_capped(db_session, make_template, make_channel):
    await _seed(db_session, make_template, make_channel, "long_msg")
    r = await fire(FireEnvelope(type="long_msg", context={"log": "ș" * 40_000}), db_session)
    await db_session.commit()
    row = (await db_session.execute(select(NotificationLog).where(NotificationLog.id == r.id))).scalar_one()
    assert len(row.message.encode("utf-8")) <= MESSAGE_MAX_BYTES


@pytest.mark.mysql
async def test_a_long_message_is_not_lost_on_mysql(db_session, make_template, make_channel):
    """Dispatched and suppressed rows both go through the cap."""
    await _seed(db_session, make_template, make_channel, "long_msg_my")
    big = {"log": "ș" * 40_000}        # 80,000 bytes once rendered
    sent = await fire(FireEnvelope(type="long_msg_my", context=big), db_session)
    await db_session.commit()
    gated = await fire(FireEnvelope(type="long_msg_my", context={**big, "n": 2}, inhibited_by_active="other"),
                       db_session)
    await db_session.commit()
    rows = (await db_session.execute(select(NotificationLog))).scalars().all()
    assert {r.id for r in rows} == {sent.id, gated.id}
    assert all(len(r.message.encode("utf-8")) <= MESSAGE_MAX_BYTES for r in rows)
