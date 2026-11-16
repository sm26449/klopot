"""The per-send delivery lookup uses an index (audit P11).

``ChannelManager.dispatch`` selects from ``deliveries`` by ``idempotency_key``
on every send. With no index on that column MySQL scanned the whole table.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.models import Delivery

INDEX = "ix_delivery_idempotency_key"


def test_the_model_declares_the_index():
    by_name = {i.name: [c.name for c in i.columns] for i in Delivery.__table__.indexes}
    assert by_name[INDEX] == ["idempotency_key"]


@pytest.mark.mysql
async def test_mysql_can_use_the_index_for_the_lookup(db_session):
    rows = (await db_session.execute(text(
        "EXPLAIN SELECT id, channel, attempts, purpose FROM deliveries "
        "WHERE idempotency_key IN ('ntf_1:ui_default', 'ntf_1:sms_main')"
    ))).mappings().all()
    assert any(INDEX in (r["possible_keys"] or "") for r in rows), [dict(r) for r in rows]
