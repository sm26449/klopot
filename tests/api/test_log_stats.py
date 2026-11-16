"""F3: GET /v1/log/stats + is_test filter on /v1/log."""
from __future__ import annotations

from datetime import timedelta

from app.db.models import (
    DeliveryStatus,
    NotificationLog,
    Severity,
    SuppressedReason,
)
from app.utils.time import utc_now

_SENT = DeliveryStatus.sent


async def _seed(db_session):
    now = utc_now()
    rows = [
        NotificationLog(id="n1", type="a", severity=Severity.critical, title="t1",
                        fired_at=now, dispatched_to=["ui"], delivery_status=_SENT),
        NotificationLog(id="n2", type="a", severity=Severity.warning, title="t2",
                        fired_at=now, suppressed_reason=SuppressedReason.throttled,
                        delivery_status=DeliveryStatus.suppressed),
        NotificationLog(id="n3", type="b", severity=Severity.critical, title="t3",
                        fired_at=now, dispatched_to=["ui"], acknowledged_at=now,
                        delivery_status=_SENT),
        NotificationLog(id="n4", type="a", severity=Severity.info, title="t4",
                        fired_at=now - timedelta(days=5), dispatched_to=["ui"],
                        delivery_status=_SENT),
        NotificationLog(id="n5", type="c", severity=Severity.info, title="t5",
                        fired_at=now, dispatched_to=["ui"], is_test=True,
                        delivery_status=_SENT),
    ]
    for r in rows:
        db_session.add(r)
    await db_session.commit()


async def test_stats_24h(db_client, admin_key, db_session):
    await _seed(db_session)
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/log/stats", params={"window": "24h"}, headers=h)
    assert r.status_code == 200, r.text
    s = r.json()
    # n4 is 5 days old → excluded from a 24h window
    assert s["dispatched"] == 3           # n1, n3, n5
    assert s["suppressed_by_reason"] == {"throttled": 1}
    assert s["suppressed"] == 1
    assert s["by_severity"]["critical"] == 2
    assert s["unacked_critical"] == 1     # n1 (n3 is acked)
    top = {t["type"]: t["count"] for t in s["top_types"]}
    assert top["a"] == 2                  # n1, n2 within window (n4 excluded)


async def test_stats_window_includes_old(db_client, admin_key, db_session):
    await _seed(db_session)
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/log/stats", params={"window": "7d"}, headers=h)
    assert r.status_code == 200
    assert r.json()["dispatched"] == 4    # now includes n4


async def test_stats_bad_window_422(db_client, admin_key):
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/log/stats", params={"window": "soon"}, headers=h)
    assert r.status_code == 422


async def test_is_test_filter(db_client, admin_key, db_session):
    await _seed(db_session)
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/log", params={"is_test": "true"}, headers=h)
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()["items"]}
    assert ids == {"n5"}
    r = await db_client.get("/v1/log", params={"is_test": "false"}, headers=h)
    assert "n5" not in {e["id"] for e in r.json()["items"]}


async def test_stats_not_shadowed_by_log_id(db_client, admin_key):
    """`/log/stats` must resolve to the stats endpoint, not `/log/{id}`."""
    h = {"X-API-Key": admin_key}
    r = await db_client.get("/v1/log/stats", headers=h)
    assert r.status_code == 200
    assert "dispatched" in r.json()
