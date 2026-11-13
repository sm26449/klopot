"""ChannelManager tests — orchestrates breaker + rate-limit + dispatch."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.base import Notification, SendResult
from app.channels.manager import ChannelManager
from app.db.models import ChannelKind


def _notif():
    return Notification(
        id="ntf_test", type="t", severity="warning", icon=None,
        title="t", message="m", fired_at=datetime(2026, 5, 10, 12, 0, 0),
    )


@pytest.fixture
async def manager():
    return ChannelManager()


@pytest.fixture
async def channel_row(db_session, make_channel):
    c = make_channel(kind=ChannelKind.ui, name="ui_test")
    db_session.add(c)
    await db_session.commit()
    return c


# ── Empty / unknown channels ──────────────────────────────────────


async def test_dispatch_empty_channel_list(manager, db_session):
    out = await manager.dispatch(_notif(), [], db_session)
    assert out.succeeded == []
    assert out.failed == {}


async def test_dispatch_unknown_channel_name_recorded_as_failed(manager, db_session):
    out = await manager.dispatch(_notif(), ["does_not_exist"], db_session)
    assert "does_not_exist" in out.failed
    assert "not found" in out.failed["does_not_exist"]


async def test_dispatch_disabled_channel_recorded_as_failed(manager, db_session, make_channel):
    c = make_channel(kind=ChannelKind.ui, enabled=False)
    db_session.add(c)
    await db_session.commit()
    out = await manager.dispatch(_notif(), [c.name], db_session)
    assert "disabled" in out.failed[c.name]


# ── Successful dispatch ───────────────────────────────────────────


async def test_dispatch_success_records_in_outcome(manager, channel_row, db_session):
    """Patch the adapter's send to return ok=True."""
    fake = AsyncMock(return_value=SendResult(ok=True))
    with patch.object(manager, "_get_adapter") as get_adapter:
        adapter = type("X", (), {"send": fake})()
        get_adapter.return_value = adapter
        out = await manager.dispatch(_notif(), [channel_row.name], db_session)
    assert channel_row.name in out.succeeded
    assert channel_row.name not in out.failed


async def test_dispatch_failure_recorded_with_error(manager, channel_row, db_session):
    fake = AsyncMock(return_value=SendResult(ok=False, error="rate limit hit"))
    with patch.object(manager, "_get_adapter") as get_adapter:
        get_adapter.return_value = type("X", (), {"send": fake})()
        out = await manager.dispatch(_notif(), [channel_row.name], db_session)
    assert "rate limit hit" in out.failed[channel_row.name]


async def test_dispatch_adapter_exception_caught(manager, channel_row, db_session):
    fake = AsyncMock(side_effect=RuntimeError("boom"))
    with patch.object(manager, "_get_adapter") as get_adapter:
        get_adapter.return_value = type("X", (), {"send": fake})()
        out = await manager.dispatch(_notif(), [channel_row.name], db_session)
    assert "boom" in out.failed[channel_row.name]
    assert "RuntimeError" in out.failed[channel_row.name]


# ── Breaker integration ───────────────────────────────────────────


async def test_open_breaker_blocks_send(manager, channel_row, db_session):
    """Force the breaker open before dispatch — adapter must NOT be
    called, and the channel is reported as DEFERRED (not failed): the
    transport was never attempted (audit F22)."""
    # Trip the breaker by recording threshold failures
    for _ in range(manager._breaker._threshold):
        await manager._breaker.record_failure(channel_row.name, "boom")

    fake = AsyncMock(return_value=SendResult(ok=True))
    with patch.object(manager, "_get_adapter") as get_adapter:
        get_adapter.return_value = type("X", (), {"send": fake})()
        out = await manager.dispatch(_notif(), [channel_row.name], db_session)
    assert "circuit_open" in out.deferred[channel_row.name]
    assert channel_row.name not in out.failed
    fake.assert_not_called()


async def test_consecutive_failures_open_breaker(manager, channel_row, db_session):
    """Threshold consecutive failures should flip the breaker to open."""
    fake = AsyncMock(return_value=SendResult(ok=False, error="boom"))
    with patch.object(manager, "_get_adapter") as get_adapter:
        get_adapter.return_value = type("X", (), {"send": fake})()
        for _ in range(manager._breaker._threshold):
            await manager.dispatch(_notif(), [channel_row.name], db_session)
    assert manager._breaker.state(channel_row.name).state == "open"


# ── Rate limiter integration ──────────────────────────────────────


async def test_rate_limited_channel_blocked(manager, db_session, make_channel):
    c = make_channel(kind=ChannelKind.ui, rate_limit_per_min=1)
    db_session.add(c)
    await db_session.commit()

    fake = AsyncMock(return_value=SendResult(ok=True))
    with patch.object(manager, "_get_adapter") as get_adapter:
        get_adapter.return_value = type("X", (), {"send": fake})()
        out1 = await manager.dispatch(_notif(), [c.name], db_session)
        out2 = await manager.dispatch(_notif(), [c.name], db_session)
    assert c.name in out1.succeeded
    # Rate-limited is a deferral, not a transport failure (audit F22).
    assert "rate_limited" in out2.deferred[c.name]
    assert c.name not in out2.failed


# ── Adapter caching ───────────────────────────────────────────────


async def test_get_adapter_caches_per_kind(manager):
    a1 = manager._get_adapter("ui")
    a2 = manager._get_adapter("ui")
    assert a1 is a2


async def test_get_adapter_unknown_kind_returns_none(manager):
    assert manager._get_adapter("does_not_exist") is None


# ── Health surface ────────────────────────────────────────────────


async def test_health_overall_lists_loaded_kinds(manager):
    manager._get_adapter("ui")
    h = manager.health(None)
    assert "adapter_kinds_loaded" in h


async def test_health_per_channel(manager):
    h = manager.health("some_channel")
    assert "breaker" in h
    assert "rate_used" in h


# ── A34: per-route channel_overrides ──────────────────────────────


async def test_dispatch_applies_channel_overrides(manager, db_session, make_channel):
    """Per-route channel_overrides shallow-merge over the channel config
    before the adapter sends (audit A34)."""
    c = make_channel(kind=ChannelKind.ui, name="ov_ch", config={"a": 1, "b": 2})
    db_session.add(c)
    await db_session.commit()

    fake = AsyncMock(return_value=SendResult(ok=True))
    with patch.object(manager, "_get_adapter") as get_adapter:
        get_adapter.return_value = type("X", (), {"send": fake})()
        out = await manager.dispatch(
            _notif(), [c.name], db_session,
            overrides_by_name={c.name: {"b": 99, "c": 3}},
        )
    assert out.succeeded == [c.name]
    sent_cfg = fake.call_args.args[1]
    assert sent_cfg == {"a": 1, "b": 99, "c": 3}


async def test_dispatch_without_overrides_uses_channel_config(
    manager, db_session, make_channel
):
    c = make_channel(kind=ChannelKind.ui, name="base_ch", config={"a": 1})
    db_session.add(c)
    await db_session.commit()

    fake = AsyncMock(return_value=SendResult(ok=True))
    with patch.object(manager, "_get_adapter") as get_adapter:
        get_adapter.return_value = type("X", (), {"send": fake})()
        await manager.dispatch(_notif(), [c.name], db_session)
    assert fake.call_args.args[1] == {"a": 1}
