"""Tests for app.core.digest — daily suppressed-alerts digest."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.core.digest import DigestService
from app.db.models import (
    DeliveryStatus,
    NotificationLog,
    Severity,
    SuppressedReason,
)
from app.utils.time import utc_now


def _row(id_: str, *, type_: str = "t1", suppressed=None, age_h: int = 1):
    return NotificationLog(
        id=id_,
        type=type_,
        severity=Severity.warning,
        title="x",
        vars_payload={},
        dispatched_to=[] if suppressed else ["ui_default"],
        failed_channels={},
        suppressed_reason=suppressed,
        delivery_status=DeliveryStatus.suppressed if suppressed else DeliveryStatus.sent,
        fired_at=utc_now() - timedelta(hours=age_h),
    )


async def test_compute_context_counts(db_session):
    db_session.add_all([
        _row("d1"),
        _row("d2"),
        _row("s1", suppressed=SuppressedReason.throttled),
        _row("s2", suppressed=SuppressedReason.throttled, type_="t2"),
        _row("s3", suppressed=SuppressedReason.inhibited, type_="t2"),
        _row("old", suppressed=SuppressedReason.throttled, age_h=30),  # outside 24h
    ])
    await db_session.commit()

    ctx = await DigestService().compute_context()

    assert ctx["dispatched"] == 2
    assert ctx["total_suppressed"] == 3
    assert "throttled=2" in ctx["by_reason"]
    assert "inhibited=1" in ctx["by_reason"]
    assert "t2×2" in ctx["top_types"]


async def test_tick_fires_only_at_configured_hour(db_session):
    from zoneinfo import ZoneInfo

    from app.config import get_settings

    svc = DigestService()
    tz = ZoneInfo(get_settings().tz)
    hour = get_settings().digest_hour

    fake_fire = AsyncMock(return_value=type("R", (), {"dispatched": True})())
    with patch("app.core.dispatcher.fire", fake_fire):
        # Wrong hour → no fire
        wrong = datetime(2026, 7, 6, (hour + 3) % 24, 10, tzinfo=tz)
        assert await svc.tick(now_local=wrong) is False
        fake_fire.assert_not_awaited()

        # Right hour → fires
        right = datetime(2026, 7, 6, hour, 10, tzinfo=tz)
        assert await svc.tick(now_local=right) is True
        fake_fire.assert_awaited_once()
        env = fake_fire.await_args.args[0]
        assert env.type == "daily_suppressed_digest"
        assert env.source == "digest"


async def test_tick_skips_if_sent_recently(db_session):
    from zoneinfo import ZoneInfo

    from app.config import get_settings

    db_session.add(_row("prev", type_="daily_suppressed_digest", age_h=2))
    await db_session.commit()

    svc = DigestService()
    tz = ZoneInfo(get_settings().tz)
    right = datetime(2026, 7, 6, get_settings().digest_hour, 10, tzinfo=tz)

    fake_fire = AsyncMock()
    with patch("app.core.dispatcher.fire", fake_fire):
        assert await svc.tick(now_local=right) is False
    fake_fire.assert_not_awaited()
