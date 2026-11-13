"""Tests for app.core.escalation — re-page unacked criticals."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.channels.manager import DispatchOutcome
from app.core.escalation import EscalationService
from app.db.models import NotificationLog, Severity
from app.utils.time import utc_now


def _row(
    *,
    id_: str,
    severity: Severity = Severity.critical,
    age_min: int = 30,
    acknowledged: bool = False,
    escalated: bool = False,
    is_test: bool = False,
    suppressed=None,
) -> NotificationLog:
    now = utc_now()
    return NotificationLog(
        id=id_,
        type="t_esc",
        severity=severity,
        title=f"critical {id_}",
        message="boom",
        vars_payload={},
        dispatched_to=["telegram_main"],
        failed_channels={},
        suppressed_reason=suppressed,
        fired_at=now - timedelta(minutes=age_min),
        acknowledged_at=(now - timedelta(minutes=5)) if acknowledged else None,
        escalated_at=(now - timedelta(minutes=5)) if escalated else None,
        is_test=is_test,
    )


@pytest.fixture
def fake_manager():
    mgr = AsyncMock()
    mgr.dispatch = AsyncMock(
        return_value=DispatchOutcome(succeeded=["sms_main"], failed={})
    )
    return mgr


async def _sweep(fake_manager) -> int:
    svc = EscalationService()
    with patch(
        "app.channels.manager.get_channel_manager", return_value=fake_manager
    ):
        return await svc.sweep_once()


async def test_escalates_old_unacked_critical(db_session, fake_manager):
    db_session.add(_row(id_="n1", age_min=30))
    await db_session.commit()

    n = await _sweep(fake_manager)

    assert n == 1
    fake_manager.dispatch.assert_awaited_once()
    notif, channels, _ = fake_manager.dispatch.await_args.args
    assert channels == ["sms_main"]
    assert notif.title.startswith("ESCALATION (unacked")
    row = (
        await db_session.execute(
            select(NotificationLog).where(NotificationLog.id == "n1")
        )
    ).scalar_one()
    assert row.escalated_at is not None


@pytest.mark.parametrize(
    ("kwargs", "why"),
    [
        ({"acknowledged": True}, "acked"),
        ({"escalated": True}, "already escalated"),
        ({"is_test": True}, "test fire"),
        ({"severity": Severity.warning}, "not critical"),
        ({"age_min": 5}, "younger than escalation_after_min"),
        ({"age_min": 60 * 25}, "older than 24h backstop"),
    ],
)
async def test_not_escalated(db_session, fake_manager, kwargs, why):
    db_session.add(_row(id_="n2", **kwargs))
    await db_session.commit()

    n = await _sweep(fake_manager)

    assert n == 0, f"should skip: {why}"
    fake_manager.dispatch.assert_not_awaited()


async def test_suppressed_row_not_escalated(db_session, fake_manager):
    from app.db.models import SuppressedReason

    db_session.add(_row(id_="n3", suppressed=SuppressedReason.throttled))
    await db_session.commit()
    assert await _sweep(fake_manager) == 0


async def test_stamps_even_when_dispatch_fails(db_session, fake_manager):
    """One escalation per row EVER — a dead SMS channel must not
    cause a retry burst on recovery."""
    fake_manager.dispatch = AsyncMock(
        return_value=DispatchOutcome(succeeded=[], failed={"sms_main": "down"})
    )
    db_session.add(_row(id_="n4", age_min=30))
    await db_session.commit()

    assert await _sweep(fake_manager) == 1
    row = (
        await db_session.execute(
            select(NotificationLog).where(NotificationLog.id == "n4")
        )
    ).scalar_one()
    assert row.escalated_at is not None
    # Second sweep: nothing left to escalate, no second dispatch
    assert await _sweep(fake_manager) == 0
    fake_manager.dispatch.assert_awaited_once()


async def test_disabled_when_after_min_zero(db_session, fake_manager):
    from app.config import get_settings

    db_session.add(_row(id_="n5", age_min=30))
    await db_session.commit()
    settings = get_settings()
    old = settings.escalation_after_min
    object.__setattr__(settings, "escalation_after_min", 0)
    try:
        assert await _sweep(fake_manager) == 0
    finally:
        object.__setattr__(settings, "escalation_after_min", old)

async def test_disabled_when_channel_empty(db_session, fake_manager):
    """C-08: with no escalation channel configured, the sweep does nothing
    instead of trying to dispatch to a missing channel."""
    from app.config import get_settings

    db_session.add(_row(id_="n6", age_min=30))
    await db_session.commit()
    settings = get_settings()
    old = settings.escalation_channel
    object.__setattr__(settings, "escalation_channel", "")
    try:
        assert await _sweep(fake_manager) == 0
    finally:
        object.__setattr__(settings, "escalation_channel", old)
