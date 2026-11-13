"""Regression tests for audit findings A02 (dedup confuses
test/real/suppressed) and A03 (failed delivery reported as success).

Reproduced from the audit artifacts: ``api-results.json → test_then_real,
disabled_then_enabled`` and ``extra-results.json → failure_retry``.

The channel manager is mocked (same pattern as test_dispatcher.py) so a
test can force "all failed", "partial", or "all ok" outcomes.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.channels.manager import DispatchOutcome
from app.core.delivery_status import (
    compute_delivery_status,
    should_coalesce,
)
from app.core.dispatcher import FireEnvelope, fire
from app.db.models import (
    ChannelKind,
    DeliveryStatus,
    NotificationLog,
    Severity,
    SuppressedReason,
    TemplateChannel,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
async def template_with_channel(db_session, make_template, make_channel):
    t = make_template(min_repeat_min=0)
    c = make_channel(kind=ChannelKind.ui)
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(
        TemplateChannel(
            template_id=t.id, channel_id=c.id,
            severity_min=Severity.info, enabled=True,
        )
    )
    await db_session.commit()
    await db_session.refresh(t)
    return t, c


async def _ok(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    return DispatchOutcome(succeeded=list(channel_names), failed={})


async def _all_fail(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    return DispatchOutcome(
        succeeded=[], failed={c: "channel disabled" for c in channel_names}
    )


async def _row(db_session, notif_id):
    return (
        await db_session.execute(
            select(NotificationLog).where(NotificationLog.id == notif_id)
        )
    ).scalar_one()


# ── A03 — failed delivery is NOT a success ────────────────────────


async def test_all_channels_fail_is_failed_not_sent(template_with_channel, db_session):
    """A fire whose every channel errors must report dispatched=False /
    status=failed, and persist delivery_status=failed with no
    suppressed_reason — NOT a phantom success (audit A03)."""
    t, c = template_with_channel
    with patch("app.channels.manager.ChannelManager.dispatch", new=_all_fail):
        r = await fire(FireEnvelope(type=t.type, context={"k": 1}), db_session)
    await db_session.commit()

    assert r.dispatched is False
    assert r.status == "failed"
    assert r.channels == []
    row = await _row(db_session, r.id)
    assert row.suppressed_reason is None
    assert row.delivery_status == DeliveryStatus.failed
    assert row.dispatched_to == []
    assert c.name in row.failed_channels


async def test_partial_dedup_replays_real_status(template_with_channel, db_session, make_channel):
    """Dedup replay returns the REAL settled status, not 'not
    suppressed ⇒ dispatched' (audit A03). A partial fire replays as
    partial with the actually-succeeded channels."""
    t, c = template_with_channel
    c2 = make_channel(kind=ChannelKind.telegram, name="tg")
    db_session.add(c2)
    await db_session.flush()
    db_session.add(TemplateChannel(
        template_id=t.id, channel_id=c2.id,
        severity_min=Severity.info, enabled=True,
    ))
    await db_session.commit()

    async def _partial(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
        return DispatchOutcome(
            succeeded=[channel_names[0]], failed={channel_names[1]: "channel disabled"}
        )

    env = FireEnvelope(type=t.type, context={"k": "same"})
    with patch("app.channels.manager.ChannelManager.dispatch", new=_partial):
        first = await fire(env, db_session)
        await db_session.commit()
        second = await fire(env, db_session)  # within window → coalesce

    assert second.id == first.id              # coalesced (a success is idempotent)
    assert second.status == "partial"
    assert second.dispatched is True
    assert second.channels == first.channels != []


async def test_failed_fire_not_coalesced_allows_retry(template_with_channel, db_session):
    """A later identical fire must NOT dedup onto a prior FAILED row —
    otherwise recovery never happens (audit A02/A03). It re-attempts
    delivery as a fresh row."""
    t, _ = template_with_channel
    env = FireEnvelope(type=t.type, context={"k": "retry"})
    with patch("app.channels.manager.ChannelManager.dispatch", new=_all_fail):
        first = await fire(env, db_session)
        await db_session.commit()
        second = await fire(env, db_session)
    await db_session.commit()

    assert second.id != first.id              # fresh fire, not the stale failed row
    assert second.status == "failed"


# ── A02 — dedup must not confuse test / real / suppressed ─────────


async def test_real_fire_does_not_coalesce_onto_test(template_with_channel, db_session):
    """A real fire after a test fire with the same type/context must be
    its own row (audit A02 test_then_real) — not inherit the test row."""
    t, _ = template_with_channel
    ctx = {"k": "v"}
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        test_fire = await fire(FireEnvelope(type=t.type, context=ctx, test=True), db_session)
        await db_session.commit()
        real_fire = await fire(FireEnvelope(type=t.type, context=ctx, test=False), db_session)
    await db_session.commit()

    assert real_fire.id != test_fire.id
    assert (await _row(db_session, test_fire.id)).is_test is True
    real_row = await _row(db_session, real_fire.id)
    assert real_row.is_test is False
    assert real_row.delivery_status == DeliveryStatus.sent


async def test_reenabled_template_fires_after_suppression(template_with_channel, db_session):
    """Disabled → suppressed row; re-enable → the next identical fire
    must DELIVER, not replay the stale 'disabled' row (audit A02
    disabled_then_enabled)."""
    t, _ = template_with_channel
    t.enabled = False
    await db_session.commit()

    ctx = {"k": "v"}
    disabled_fire = await fire(FireEnvelope(type=t.type, context=ctx), db_session)
    await db_session.commit()
    assert disabled_fire.suppressed_reason == "disabled"

    t.enabled = True
    await db_session.commit()
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        enabled_fire = await fire(FireEnvelope(type=t.type, context=ctx), db_session)
    await db_session.commit()

    assert enabled_fire.id != disabled_fire.id
    assert enabled_fire.dispatched is True
    assert enabled_fire.status == "sent"


async def test_suppressed_storm_still_coalesces(template_with_channel, db_session):
    """The fix must NOT regress 'one row per storm': repeated identical
    fires that are suppressed for the SAME reason still dedup to one
    row (otherwise a sustained disable/throttle floods the log)."""
    t, _ = template_with_channel
    t.enabled = False
    await db_session.commit()

    ctx = {"k": "v"}
    first = await fire(FireEnvelope(type=t.type, context=ctx), db_session)
    await db_session.commit()
    second = await fire(FireEnvelope(type=t.type, context=ctx), db_session)
    await db_session.commit()

    assert second.id == first.id
    assert second.suppressed_reason == "disabled"


# ── Pure helpers ──────────────────────────────────────────────────


def test_compute_delivery_status_matrix():
    assert compute_delivery_status("throttled", [], {}) == DeliveryStatus.suppressed
    assert compute_delivery_status(None, ["ui"], {}) == DeliveryStatus.sent
    assert compute_delivery_status(None, ["ui"], {"tg": "x"}) == DeliveryStatus.partial
    assert compute_delivery_status(None, [], {"tg": "x"}) == DeliveryStatus.failed
    assert compute_delivery_status(None, [], {}) == DeliveryStatus.failed


def test_should_coalesce_disposition_rules():
    sent = NotificationLog(
        id="a", type="t", severity=Severity.info, title="x",
        dispatched_to=["ui"], failed_channels={}, suppressed_reason=None,
        delivery_status=DeliveryStatus.sent,
    )
    failed = NotificationLog(
        id="b", type="t", severity=Severity.info, title="x",
        dispatched_to=[], failed_channels={"ui": "503"}, suppressed_reason=None,
        delivery_status=DeliveryStatus.failed,
    )
    disabled = NotificationLog(
        id="c", type="t", severity=Severity.info, title="x",
        dispatched_to=[], failed_channels={},
        suppressed_reason=SuppressedReason.disabled,
        delivery_status=DeliveryStatus.suppressed,
    )
    # A would-dispatch fire coalesces only onto a prior success.
    assert should_coalesce(sent, None) is True
    assert should_coalesce(failed, None) is False
    assert should_coalesce(disabled, None) is False
    # A suppressed fire coalesces only onto the same reason.
    assert should_coalesce(disabled, "disabled") is True
    assert should_coalesce(disabled, "throttled") is False
    assert should_coalesce(sent, "disabled") is False
