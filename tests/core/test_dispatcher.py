"""Tests for app.core.dispatcher.fire().

The channel manager is mocked so we don't depend on real adapters
(telegram bot, sms gateway, etc.). Mock returns a DispatchOutcome
shaped however the test needs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.channels.manager import DispatchOutcome
from app.core.dispatcher import FireEnvelope, fire
from app.db.models import (
    ChannelKind,
    NotificationLog,
    Severity,
    SuppressedReason,
    TemplateChannel,
)


@pytest.fixture
async def template_with_channel(db_session, make_template, make_channel):
    """Template + Channel + TemplateChannel link, all enabled and
    routed at info-min."""
    t = make_template(min_repeat_min=0)
    c = make_channel(kind=ChannelKind.ui)
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(
        TemplateChannel(
            template_id=t.id,
            channel_id=c.id,
            severity_min=Severity.info,
            enabled=True,
        )
    )
    await db_session.commit()
    await db_session.refresh(t)
    return t, c


@pytest.fixture
def fake_dispatch_ok():
    """Mock ChannelManager.dispatch → returns 'all succeeded'."""

    async def _dispatch(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
        return DispatchOutcome(succeeded=list(channel_names), failed={})

    return _dispatch


# ── Happy path ────────────────────────────────────────────────────


async def test_fire_unknown_type_returns_synthetic_result(db_session):
    env = FireEnvelope(type="never_registered", context={"x": 1})
    r = await fire(env, db_session)
    await db_session.commit()  # the endpoint commits after fire (autoflush=False)
    assert r.dispatched is False
    assert r.suppressed_reason == "unknown_type"
    # An audit row IS written (tagged unknown_type) so the operator can
    # see the attempt — but nothing is dispatched.
    rows = (
        await db_session.execute(select(NotificationLog))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].type == "never_registered"
    assert rows[0].suppressed_reason == SuppressedReason.unknown_type
    assert rows[0].template_id is None
    assert rows[0].dispatched_to == []


async def test_fire_known_type_writes_log_row(template_with_channel, db_session, fake_dispatch_ok):
    t, c = template_with_channel
    env = FireEnvelope(type=t.type, context={"name": "test", "value": 42})
    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
        r = await fire(env, db_session)
    await db_session.commit()
    assert r.dispatched is True
    assert c.name in r.channels
    assert "test fired" in r.title
    assert "value=42" in r.message
    row = (
        await db_session.execute(select(NotificationLog).where(NotificationLog.id == r.id))
    ).scalar_one()
    assert row.suppressed_reason is None
    assert row.dispatched_to == [c.name]
    assert row.dispatch_latency_ms is not None


async def test_fire_failed_channels_recorded(template_with_channel, db_session, make_channel):
    t, c = template_with_channel
    c2 = make_channel(kind=ChannelKind.telegram, name="telegram_test")
    db_session.add(c2)
    await db_session.flush()
    db_session.add(
        TemplateChannel(
            template_id=t.id, channel_id=c2.id,
            severity_min=Severity.info, enabled=True,
        )
    )
    await db_session.commit()

    async def partial(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
        return DispatchOutcome(
            succeeded=[channel_names[0]],
            failed={channel_names[1]: "channel disabled"},
        )

    with patch("app.channels.manager.ChannelManager.dispatch", new=partial):
        r = await fire(FireEnvelope(type=t.type, context={}), db_session)
    await db_session.commit()
    row = (
        await db_session.execute(select(NotificationLog).where(NotificationLog.id == r.id))
    ).scalar_one()
    assert len(row.dispatched_to) == 1
    # A permanent failure settles immediately into failed_channels (a
    # retryable error would stay pending for the worker — A01).
    assert "channel disabled" in str(row.failed_channels)


# ── Gating outcomes ───────────────────────────────────────────────


async def test_disabled_template_writes_suppressed_row(template_with_channel, db_session):
    t, _ = template_with_channel
    t.enabled = False
    await db_session.commit()
    r = await fire(FireEnvelope(type=t.type, context={}), db_session)
    await db_session.commit()
    assert r.dispatched is False
    assert r.suppressed_reason == "disabled"
    row = (
        await db_session.execute(select(NotificationLog).where(NotificationLog.id == r.id))
    ).scalar_one()
    assert row.suppressed_reason.value == "disabled"


async def test_throttled_writes_suppressed_row(template_with_channel, db_session):
    from app.db.models import ThrottleState

    t, _ = template_with_channel
    t.min_repeat_min = 30
    db_session.add(
        ThrottleState(type=t.type, last_fired_at=datetime.utcnow())
    )
    await db_session.commit()
    r = await fire(FireEnvelope(type=t.type, context={}), db_session)
    assert r.suppressed_reason == "throttled"


async def test_an_admin_test_fire_bypasses_throttle(template_with_channel, db_session, fake_dispatch_ok):
    from app.db.models import ThrottleState

    t, _ = template_with_channel
    t.min_repeat_min = 30
    db_session.add(
        ThrottleState(type=t.type, last_fired_at=datetime.utcnow())
    )
    await db_session.commit()
    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
        r = await fire(
            FireEnvelope(type=t.type, context={}, test=True, override_silencing=True),
            db_session,
        )
    assert r.dispatched is True


# ── Idempotency ───────────────────────────────────────────────────


async def test_idempotent_same_vars_returns_existing(template_with_channel, db_session, fake_dispatch_ok):
    t, _ = template_with_channel
    env = FireEnvelope(type=t.type, context={"k": "v"})

    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
        first = await fire(env, db_session)
        await db_session.commit()
        second = await fire(env, db_session)

    assert second.id == first.id


async def test_idempotency_window_expired_creates_new(template_with_channel, db_session, fake_dispatch_ok):
    """A row older than 5 minutes does NOT count for idempotency."""
    t, _ = template_with_channel
    env = FireEnvelope(type=t.type, context={"k": "v"})

    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
        first = await fire(env, db_session)
        await db_session.commit()
        first_row = (
            await db_session.execute(
                select(NotificationLog).where(NotificationLog.id == first.id)
            )
        ).scalar_one()
        first_row.fired_at = datetime.utcnow() - timedelta(minutes=10)
        # The admission claim (R01) ages with the log in production — age it
        # too so the second fire re-claims the stale slot.
        from app.db.models import DedupClaim
        for claim in (
            await db_session.execute(select(DedupClaim))
        ).scalars().all():
            claim.claimed_at = datetime.utcnow() - timedelta(minutes=10)
        await db_session.commit()
        second = await fire(env, db_session)

    assert second.id != first.id


async def test_different_vars_no_idempotency(template_with_channel, db_session, fake_dispatch_ok):
    t, _ = template_with_channel
    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
        a = await fire(FireEnvelope(type=t.type, context={"k": "1"}), db_session)
        await db_session.commit()
        b = await fire(FireEnvelope(type=t.type, context={"k": "2"}), db_session)
    assert a.id != b.id


async def test_claim_fire_resolves_single_winner(db_session):
    """R01: concurrent identical fires resolve to one winner; a stale slot is
    re-claimed."""
    from datetime import datetime, timedelta

    from app.core.dedup_claims import claim_fire

    now = datetime(2030, 1, 1, 12, 0, 0)
    cutoff = now - timedelta(minutes=5)

    assert await claim_fire(db_session, "t", "h1", "ntf_A", now, cutoff, test=False) == "ntf_A"
    # Same context within the window → coalesce onto the first winner.
    assert await claim_fire(db_session, "t", "h1", "ntf_B", now, cutoff, test=False) == "ntf_A"
    # Different context is independent.
    assert await claim_fire(db_session, "t", "h2", "ntf_C", now, cutoff, test=False) == "ntf_C"
    # Later, the first slot is stale → re-claimed by a new fire.
    now2 = now + timedelta(minutes=10)
    assert await claim_fire(
        db_session, "t", "h1", "ntf_D", now2, now2 - timedelta(minutes=5), test=False,
    ) == "ntf_D"


async def test_fire_coalesces_onto_a_live_claim(template_with_channel, db_session, fake_dispatch_ok):
    """R01: a fire whose slot is already claimed by a concurrent winner
    coalesces onto it and does not create a second notification."""
    from app.core.dispatcher import _json_safe, _vars_hash
    from app.db.models import DedupClaim
    from app.utils.time import utc_now

    t, _ = template_with_channel
    ctx = {"k": "race"}
    h = _vars_hash(_json_safe(ctx))
    db_session.add(DedupClaim(
        type=t.type, is_test=False, context_hash=h,
        notification_id="ntf_winner", claimed_at=utc_now(),
    ))
    await db_session.commit()

    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
        r = await fire(FireEnvelope(type=t.type, context=ctx), db_session)

    assert r.id == "ntf_winner"
    assert r.dispatched is False
    # No NotificationLog was created for this coalesced fire.
    n = (await db_session.execute(
        select(func.count()).select_from(NotificationLog)
    )).scalar_one()
    assert n == 0


async def test_dedup_matches_context_beyond_five_recent(
    template_with_channel, db_session, fake_dispatch_ok
):
    """F24: context A still dedups even after >5 other distinct contexts
    fired for the same type within the window — the old limit(5) scan
    dropped A from the candidate set and re-sent it."""
    t, _ = template_with_channel
    env_a = FireEnvelope(type=t.type, context={"k": "A"})
    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
        first = await fire(env_a, db_session)
        await db_session.commit()
        # Six more distinct contexts (B..G) push A past a 5-row window.
        for k in ["B", "C", "D", "E", "F", "G"]:
            await fire(FireEnvelope(type=t.type, context={"k": k}), db_session)
            await db_session.commit()
        again = await fire(env_a, db_session)

    assert again.id == first.id  # deduped onto the original, not re-sent


# ── Severity routing ──────────────────────────────────────────────


async def test_severity_min_filter_drops_channel(db_session, make_template, make_channel):
    """A channel routed at severity_min=critical must NOT receive a
    warning-severity fire."""
    t = make_template(severity=Severity.warning, min_repeat_min=0)
    c = make_channel(kind=ChannelKind.ui)
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(
        TemplateChannel(
            template_id=t.id, channel_id=c.id,
            severity_min=Severity.critical, enabled=True,
        )
    )
    await db_session.commit()

    r = await fire(FireEnvelope(type=t.type, context={}), db_session)
    assert r.suppressed_reason == "gated"


# ── Helpers ───────────────────────────────────────────────────────


def test_vars_hash_canonical():
    """Same dict in different key orders → same hash (idempotency
    relies on this)."""
    from app.core.dispatcher import _vars_hash

    a = _vars_hash({"x": 1, "y": 2})
    b = _vars_hash({"y": 2, "x": 1})
    assert a == b


def test_vars_hash_different_values_different_hash():
    from app.core.dispatcher import _vars_hash

    assert _vars_hash({"x": 1}) != _vars_hash({"x": 2})


def test_json_safe_handles_datetime():
    from app.core.dispatcher import _json_safe

    out = _json_safe({"when": datetime(2026, 1, 1, 12, 0, 0)})
    assert isinstance(out["when"], str)
    assert "2026" in out["when"]


# ── fired_at must be UTC (regression: migration 0005) ────────────


async def test_fired_at_is_utc_on_all_paths(template_with_channel, db_session, fake_dispatch_ok):
    """All three NotificationLog creation paths must stamp fired_at
    with app-side UTC, never the server-local column default (which
    skewed the idempotency window by the UTC offset)."""
    from app.utils.time import utc_now

    t, c = template_with_channel

    # 1. dispatched path
    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
        r1 = await fire(FireEnvelope(type=t.type, context={"p": 1}), db_session)
    # 2. unknown-type path
    r2 = await fire(FireEnvelope(type="no_such_type_utc", context={}), db_session)
    await db_session.commit()

    for notif_id in (r1.id, r2.id):
        row = (
            await db_session.execute(
                select(NotificationLog).where(NotificationLog.id == notif_id)
            )
        ).scalar_one()
        delta = abs((utc_now() - row.fired_at).total_seconds())
        assert delta < 10, f"{notif_id}: fired_at {row.fired_at} not UTC-now (Δ{delta}s)"


# ── Inhibition path ───────────────────────────────────────────────


async def test_inhibited_envelope_suppresses_without_dispatch(
    template_with_channel, db_session
):
    from unittest.mock import AsyncMock

    t, _ = template_with_channel
    env = FireEnvelope(
        type=t.type, context={"name": "x", "value": 1},
        inhibited_by_active="storm_root",
    )
    fake_dispatch = AsyncMock()
    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch):
        r = await fire(env, db_session)
    await db_session.commit()

    assert r.dispatched is False
    assert r.suppressed_reason == "inhibited"
    fake_dispatch.assert_not_called()

    row = (
        await db_session.execute(
            select(NotificationLog).where(NotificationLog.id == r.id)
        )
    ).scalar_one()
    assert row.suppressed_reason == SuppressedReason.inhibited
    assert "[inhibited by storm_root]" in row.message
    assert row.dispatched_to == []


# ── A35: trace_id correlation ─────────────────────────────────────


async def test_fire_populates_trace_id_from_contextvar(
    template_with_channel, db_session, fake_dispatch_ok
):
    from app.logging_setup import trace_id_var

    t, _ = template_with_channel
    token = trace_id_var.set("trace_abc123")
    try:
        with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
            await fire(FireEnvelope(type=t.type, context={"x": 1}), db_session)
    finally:
        trace_id_var.reset(token)

    row = (await db_session.execute(select(NotificationLog))).scalars().one()
    assert row.trace_id == "trace_abc123"


async def test_fire_mints_trace_id_without_context(
    template_with_channel, db_session, fake_dispatch_ok
):
    """Engine fires have no request contextvar — the row still gets a
    non-null trace id so it's correlatable."""
    t, _ = template_with_channel
    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
        await fire(FireEnvelope(type=t.type, context={"x": 2}), db_session)
    row = (await db_session.execute(select(NotificationLog))).scalars().one()
    assert row.trace_id is not None and len(row.trace_id) > 0


async def test_unknown_type_row_also_gets_trace_id(db_session):
    await fire(FireEnvelope(type="never_registered", context={"x": 1}), db_session)
    await db_session.commit()  # the endpoint commits after fire (autoflush=False)
    row = (await db_session.execute(select(NotificationLog))).scalars().one()
    assert row.trace_id is not None


async def test_two_rules_sharing_a_template_are_not_merged(template_with_channel, db_session, fake_dispatch_ok, make_rule):
    """RL-13: two rules with the same template and the same context (e.g. both
    with an empty vars_extract) each get their notification; before, the
    second was merged into the first one's row without a trace."""
    t, _ = template_with_channel
    r1, r2 = make_rule(template_type=t.type), make_rule(template_type=t.type)
    db_session.add_all([r1, r2])
    await db_session.commit()
    ctx = {"name": "shared", "value": 1}
    with patch("app.channels.manager.ChannelManager.dispatch", new=fake_dispatch_ok):
        a = await fire(FireEnvelope(type=t.type, context=ctx, rule_id=r1.id, source="engine"), db_session)
        await db_session.commit()
        b = await fire(FireEnvelope(type=t.type, context=ctx, rule_id=r2.id, source="engine"), db_session)
        await db_session.commit()
        again = await fire(FireEnvelope(type=t.type, context=ctx, rule_id=r2.id, source="engine"), db_session)
        await db_session.commit()
    assert a.id != b.id and a.dispatched and b.dispatched
    assert again.id == b.id          # the same rule still de-duplicates
    rows = (await db_session.execute(select(NotificationLog).where(NotificationLog.type == t.type))).scalars().all()
    assert {r.rule_id for r in rows} == {r1.id, r2.id}
