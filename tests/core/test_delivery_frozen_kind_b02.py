"""B-02: a delivery must be retried through the adapter KIND it was admitted
against, not the live channel row's kind.

The outbox froze each delivery's effective config (V01) but chose the adapter
from the live channel. Repurposing a channel (webhook → ui) while a delivery was
pending made the worker feed the frozen webhook config to the ui adapter, which
reported success — a false ``sent`` with nothing delivered. The fix freezes the
adapter kind too and dispatches through it.
"""
from __future__ import annotations

from unittest.mock import patch

from app.channels.base import Notification, SendResult
from app.channels.manager import get_channel_manager
from app.core import outbox
from app.db.models import ChannelKind, Delivery
from app.utils.time import utc_now


def _notif() -> Notification:
    return Notification(
        id="b02note", type="t", severity="warning", icon=None,
        title="x", message="y", fired_at=utc_now(),
    )


class _StubAdapter:
    def __init__(self):
        self.seen_cfgs: list[dict] = []

    async def send(self, notif, cfg, idempotency_key=None):
        self.seen_cfgs.append(cfg)
        return SendResult(ok=True)


async def test_dispatch_routes_through_frozen_kind_not_live_channel(db_session, make_channel):
    """The channel is now 'ui', but the delivery was frozen as 'webhook': the
    webhook adapter (and the frozen webhook config) must be used — never the live
    ui adapter."""
    ch = make_channel(kind=ChannelKind.ui, name="b02_repurposed")
    db_session.add(ch)
    await db_session.commit()

    mgr = get_channel_manager()
    requested: list[str] = []
    stub = _StubAdapter()

    def _fake_get_adapter(kind):
        requested.append(kind)
        return stub

    with patch.object(mgr, "_get_adapter", _fake_get_adapter):
        outcome = await mgr.dispatch(
            _notif(), ["b02_repurposed"], db_session,
            effective_by_name={"b02_repurposed": {"url": "http://frozen-webhook"}},
            effective_kind_by_name={"b02_repurposed": "webhook"},
        )

    assert requested == ["webhook"]                  # frozen kind, NOT live 'ui'
    assert "b02_repurposed" in outcome.succeeded
    assert stub.seen_cfgs == [{"url": "http://frozen-webhook"}]   # frozen config


async def test_dispatch_falls_back_to_live_kind_for_legacy_rows(db_session, make_channel):
    """A delivery with no frozen kind (pre-migration) uses the live channel kind."""
    ch = make_channel(kind=ChannelKind.ui, name="b02_legacy")
    db_session.add(ch)
    await db_session.commit()

    mgr = get_channel_manager()
    requested: list[str] = []
    with patch.object(mgr, "_get_adapter", lambda k: (requested.append(k), _StubAdapter())[1]):
        await mgr.dispatch(
            _notif(), ["b02_legacy"], db_session,
            effective_by_name={"b02_legacy": {"x": 1}},   # config frozen, kind not
        )
    assert requested == ["ui"]


async def test_resolve_effective_configs_returns_kind(db_session, make_channel):
    ch = make_channel(kind=ChannelKind.webhook, name="b02_wh")
    db_session.add(ch)
    await db_session.commit()
    configs, kinds = await get_channel_manager().resolve_effective_configs(
        db_session, ["b02_wh"]
    )
    assert kinds["b02_wh"] == "webhook"
    assert "b02_wh" in configs


async def test_enqueue_freezes_the_kind_on_the_delivery(db_session):
    rows = outbox.enqueue(
        db_session, "b02note", ["b02_wh"],
        effective_by_name={"b02_wh": {"url": "x"}},
        effective_kind_by_name={"b02_wh": "webhook"},
    )
    # enqueue stamps the frozen kind onto the Delivery row it builds.
    assert rows[0].effective_kind == "webhook"
    assert isinstance(rows[0], Delivery)
