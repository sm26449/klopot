"""Regression tests for audit A04 — notification ids collided / overflowed
the schema and the rendered title was not bounded, each causing a 500.

Reproduced from ``api-results.json → concurrent_fire`` and
``boundary-results.json``.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.channels.manager import DispatchOutcome
from app.core.dispatcher import _TITLE_MAX, FireEnvelope, _generate_id, fire
from app.db.models import ChannelKind, NotificationLog, Severity, TemplateChannel

pytestmark = pytest.mark.anyio

_ID_MAX = 64  # notifications_log.id is String(64)


@pytest.fixture
async def template_with_channel(db_session, make_template, make_channel):
    def _build(**tmpl_overrides):
        return make_template(min_repeat_min=0, **tmpl_overrides)

    async def _factory(**tmpl_overrides):
        t = _build(**tmpl_overrides)
        c = make_channel(kind=ChannelKind.ui)
        db_session.add_all([t, c])
        await db_session.flush()
        db_session.add(TemplateChannel(
            template_id=t.id, channel_id=c.id,
            severity_min=Severity.info, enabled=True,
        ))
        await db_session.commit()
        await db_session.refresh(t)
        return t, c

    return _factory


async def _ok(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    return DispatchOutcome(succeeded=list(channel_names), failed={})


# ── id: unique + bounded, type-independent ────────────────────────


def test_generate_id_unique_in_same_millisecond():
    """The whole point of A04: many ids minted back-to-back (same ms)
    must not collide, and must fit String(64)."""
    ids = {_generate_id() for _ in range(5000)}
    assert len(ids) == 5000
    assert all(i.startswith("ntf_") for i in ids)
    assert all(len(i) <= _ID_MAX for i in ids)


async def test_long_type_does_not_overflow_id(template_with_channel, db_session):
    """A 64-char type used to push ``ntf_<ms>_<type>`` past String(64).
    The id is now type-independent, so it stays within bounds."""
    long_type = "t" * 64
    t, _ = await template_with_channel(type=long_type)
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        r = await fire(FireEnvelope(type=long_type, context={"k": 1}), db_session)
    await db_session.commit()
    assert len(r.id) <= _ID_MAX
    row = (await db_session.execute(
        select(NotificationLog).where(NotificationLog.id == r.id)
    )).scalar_one()
    assert row.type == long_type


async def test_unknown_type_id_bounded(db_session):
    long_type = "z" * 64
    r = await fire(FireEnvelope(type=long_type, context={}), db_session)
    await db_session.commit()
    assert r.suppressed_reason == "unknown_type"
    assert len(r.id) <= _ID_MAX


# ── title: truncated to the column width ──────────────────────────


async def test_long_rendered_title_truncated(template_with_channel, db_session):
    """A title that renders longer than 255 chars must be truncated, not
    500 on insert (MySQL ``Data too long for column 'title'``)."""
    t, _ = await template_with_channel(title_template="X" * 300)
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        r = await fire(FireEnvelope(type=t.type, context={}), db_session)
    await db_session.commit()
    assert len(r.title) == _TITLE_MAX
    row = (await db_session.execute(
        select(NotificationLog).where(NotificationLog.id == r.id)
    )).scalar_one()
    assert len(row.title) == _TITLE_MAX


async def test_normal_title_not_truncated(template_with_channel, db_session):
    t, _ = await template_with_channel(title_template="short title")
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        r = await fire(FireEnvelope(type=t.type, context={}), db_session)
    await db_session.commit()
    assert r.title == "short title"
