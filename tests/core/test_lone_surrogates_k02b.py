"""A lone UTF-16 surrogate in a payload never loses the alert (review K02b).

``json.loads`` accepts ``"\\ud800"``; such a string has no UTF-8 form, so the
database driver refused the notification row (UnicodeEncodeError, on SQLite and
MySQL alike) and the fire was lost — answered 500 to ``/v1/fire``, retried and
lost again each cycle when it came from a variable.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.dispatcher import FireEnvelope, fire
from app.db.models import Incident, NotificationLog, Severity, Template, TemplateChannel
from app.utils.text import clean_text
from tests._db import fresh

pytestmark = pytest.mark.anyio

_LONE = "a\ud800b"


def test_clean_text_replaces_only_lone_surrogates():
    assert clean_text({"k\udfff": [_LONE, "ok 🔥", 3, None]}) == {"k�": ["a�b", "ok 🔥", 3, None]}
    assert clean_text("plain") == "plain"


async def test_a_fire_with_a_lone_surrogate_is_stored(db_session, make_template, make_channel):
    tpl = make_template(type="sur", min_repeat_min=0, title_template="t {x}", message_template="m {x}")
    ch = make_channel(name="ui_sur", rate_limit_per_min=1000)
    db_session.add_all([tpl, ch])
    await db_session.flush()
    db_session.add(TemplateChannel(template_id=tpl.id, channel_id=ch.id, enabled=True, severity_min=Severity.info))
    await db_session.commit()
    r = await fire(FireEnvelope(type="sur", context={"x": _LONE}, source="src\ud800"), db_session)
    await db_session.commit()
    row = (await db_session.execute(select(NotificationLog).where(NotificationLog.id == r.id))).scalar_one()
    assert row.title == "t a�b"
    assert row.message == "m a�b"
    assert row.vars_payload == {"x": "a�b"}


async def test_an_episode_from_the_api_with_a_lone_surrogate_opens(db_client, db_session, admin_key):
    db_session.add(Template(type="disk_full", severity=Severity.critical, title_template="Disk {host}",
                            min_repeat_min=0))
    await db_session.commit()
    body = '{"type": "disk_full", "context": {"host": "h\\ud800"}, "idempotency_key": "k1"}'
    r = await db_client.post("/v1/fire", content=body,
                             headers={"X-API-Key": admin_key, "Content-Type": "application/json"})
    assert r.status_code == 202, r.text[:200]
    await fresh(db_session)
    episode = (await db_session.execute(select(Incident))).scalar_one()
    assert episode.title == "Disk h�"
    assert episode.opening_context["host"] == "h�"
