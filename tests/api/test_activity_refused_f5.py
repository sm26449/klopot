"""Refused anonymous requests are kept briefly (review F5).

Every request is an activity row; a flood of guesses (wrong keys, random
paths, wrong input tokens) was kept for log_retention_days (90). A 4xx for a
caller who was not let in now expires after activity_refused_days (1),
unless an activity rule says otherwise; everything else is unchanged.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.activity import get_activity_writer
from app.db.models import ApiRequest
from tests._db import fresh


async def _kept_days(db_session, path: str) -> float:
    await get_activity_writer().flush()
    await fresh(db_session)          # MySQL: the writer committed after this session's snapshot
    row = (await db_session.execute(
        select(ApiRequest).where(ApiRequest.path == path).order_by(ApiRequest.id.desc()))).scalars().first()
    return (row.expires_at - row.ts) / timedelta(days=1)


async def test_a_refused_anonymous_request_is_kept_a_day(db_client, db_session):
    await db_client.get("/v1/channels", headers={"X-API-Key": "alertd_" + "x" * 43})     # wrong key
    assert await _kept_days(db_session, "/v1/channels") == pytest.approx(1, abs=0.01)
    await db_client.post("/v1/inputs/999/webhook", json={})                                # no such input
    assert await _kept_days(db_session, "/v1/inputs/999/webhook") == pytest.approx(1, abs=0.01)


async def test_an_authenticated_request_keeps_the_full_retention(db_client, db_session, admin_key):
    await db_client.get("/v1/channels", headers={"X-API-Key": admin_key})
    assert await _kept_days(db_session, "/v1/channels") == pytest.approx(90, abs=0.01)
    # A path that does not exist never reaches authentication: whoever sent it,
    # it is an anonymous refusal.
    await db_client.get("/v1/no-such-thing", headers={"X-API-Key": admin_key})
    assert await _kept_days(db_session, "/v1/no-such-thing") == pytest.approx(1, abs=0.01)


async def test_a_rule_still_decides(db_client, db_session, admin_key):
    from app.core.activity_rules import get_rule_cache

    r = await db_client.post("/v1/activity/rules", headers={"X-API-Key": admin_key}, json={
        "name": "keep guesses", "match_path": "/v1/channels", "match_status": "401",
        "action": "keep", "keep_days": 30})
    assert r.status_code == 201, r.text
    get_rule_cache().invalidate()
    await db_client.get("/v1/channels", headers={"X-API-Key": "alertd_" + "y" * 43})
    assert await _kept_days(db_session, "/v1/channels") == pytest.approx(30, abs=0.01)
