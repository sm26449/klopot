"""B-10: the per-type cooldown (min_repeat_min) must be an atomic admission
boundary, not a check that only looks at the last *successful* fire.

Before the fix, two fires of the same template with DIFFERENT contexts that
raced before the first had succeeded both passed the throttle (``last_fired_at``
was still unset) and both sent, violating min_repeat_min. The fix reserves the
type atomically in the durable-intent transaction (admission-anchored), so only
one distinct fire per window is admitted; the rest are suppressed as throttled.
Identical-context fires still coalesce (the context dedup runs first), the
reservation is released on terminal failure, and a successful fire supersedes it
with the confirmed cooldown.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.channels.manager import DispatchOutcome
from app.core import gating
from app.core.dispatcher import FireEnvelope, fire
from app.db.models import ChannelKind, Severity, TemplateChannel, ThrottleState

pytestmark = pytest.mark.anyio

_DISPATCH = "app.channels.manager.ChannelManager.dispatch"


@pytest.fixture
async def routed_template(db_session, make_template, make_channel):
    """Template (min_repeat 30m) + one routed UI channel."""
    t = make_template(min_repeat_min=30)
    c = make_channel(kind=ChannelKind.ui)
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(TemplateChannel(
        template_id=t.id, channel_id=c.id, severity_min=Severity.info, enabled=True,
    ))
    await db_session.commit()
    await db_session.refresh(t)
    return t, c


async def _ok(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    return DispatchOutcome(succeeded=list(channel_names), failed={})


async def _fail(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    # Retryable failure → delivery stays pending (not terminal), so the fire is
    # admitted but has NOT recorded a success: last_fired_at stays unset.
    return DispatchOutcome(succeeded=[], failed={c: "boom" for c in channel_names})


async def _throttle_row(db_session, type_: str) -> ThrottleState | None:
    return (await db_session.execute(
        select(ThrottleState).where(ThrottleState.type == type_)
    )).scalar_one_or_none()


async def test_distinct_context_throttled_before_first_success(routed_template, db_session):
    """The core fix: a second distinct-context fire is throttled while the first
    is still in flight (no success yet). The old success-anchored throttle let
    it through — this is the regression guard."""
    t, _ = routed_template
    with patch(_DISPATCH, new=_fail):
        a = await fire(FireEnvelope(type=t.type, context={"dev": "A"}), db_session)
        await db_session.commit()
        b = await fire(FireEnvelope(type=t.type, context={"dev": "B"}), db_session)
        await db_session.commit()

    assert a.suppressed_reason is None          # first fire admitted
    assert b.suppressed_reason == "throttled"   # distinct racer suppressed

    ts = await _throttle_row(db_session, t.type)
    # Proves ADMISSION-anchoring, not success-anchoring: nothing succeeded, so
    # the confirmed cooldown is unset, yet the reservation held by the first
    # fire throttled the second.
    assert ts is not None
    assert ts.last_fired_at is None
    assert ts.reserved_by == a.id


async def test_identical_context_still_coalesces(routed_template, db_session):
    """An identical-context fire must coalesce onto the first (context dedup runs
    before the type reservation), NOT be suppressed as throttled."""
    t, _ = routed_template
    with patch(_DISPATCH, new=_fail):
        a = await fire(FireEnvelope(type=t.type, context={"dev": "A"}), db_session)
        await db_session.commit()
        b = await fire(FireEnvelope(type=t.type, context={"dev": "A"}), db_session)
        await db_session.commit()

    assert b.id == a.id
    assert b.suppressed_reason != "throttled"


async def test_no_reservation_when_min_repeat_zero(routed_template, db_session):
    """min_repeat_min=0 disables the cooldown entirely: distinct contexts both
    fire and no reservation is taken."""
    t, _ = routed_template
    t.min_repeat_min = 0
    await db_session.commit()
    with patch(_DISPATCH, new=_fail):
        a = await fire(FireEnvelope(type=t.type, context={"dev": "A"}), db_session)
        await db_session.commit()
        b = await fire(FireEnvelope(type=t.type, context={"dev": "B"}), db_session)
        await db_session.commit()

    assert a.suppressed_reason is None
    assert b.suppressed_reason is None
    assert a.id != b.id
    ts = await _throttle_row(db_session, t.type)
    assert ts is None or ts.reserved_by is None


async def test_released_reservation_admits_a_distinct_fire(routed_template, db_session):
    """Release semantics: once the reservation is released (as the dispatcher and
    worker do on terminal failure), a distinct fire is admitted again rather than
    held throttled for the whole window."""
    t, _ = routed_template
    with patch(_DISPATCH, new=_fail):
        a = await fire(FireEnvelope(type=t.type, context={"dev": "A"}), db_session)
        await db_session.commit()

        # Simulate the terminal-failure release hook.
        await gating.release_type_reservation(db_session, t.type, a.id, test=False)
        await db_session.commit()

        b = await fire(FireEnvelope(type=t.type, context={"dev": "B"}), db_session)
        await db_session.commit()

    assert b.suppressed_reason is None
    assert a.id != b.id


# ── reserve_type_slot / release unit behavior ─────────────────────────


async def test_reserve_slot_winner_loser_stale_and_release(db_session):
    now = datetime(2030, 1, 1, 12, 0, 0)
    cutoff = now - timedelta(minutes=30)

    # First fire wins the slot.
    assert await gating.reserve_type_slot(db_session, "ty", "n_A", now, cutoff, test=False) == "n_A"
    # A second within the window loses — the holder stays the first.
    assert await gating.reserve_type_slot(db_session, "ty", "n_B", now, cutoff, test=False) == "n_A"
    # Releasing by the holder frees it for the next fire.
    await gating.release_type_reservation(db_session, "ty", "n_A", test=False)
    assert await gating.reserve_type_slot(db_session, "ty", "n_C", now, cutoff, test=False) == "n_C"
    # Outside the window the slot is stale and re-reserved.
    now2 = now + timedelta(minutes=31)
    assert await gating.reserve_type_slot(
        db_session, "ty", "n_D", now2, now2 - timedelta(minutes=30), test=False,
    ) == "n_D"


async def test_confirmed_cooldown_blocks_reservation(db_session):
    """A recent successful fire (last_fired_at within the window) blocks a new
    reservation even with no in-flight reserved_at — the two share one boundary."""
    now = datetime(2030, 1, 1, 12, 0, 0)
    db_session.add(ThrottleState(type="ty", last_fired_at=now))
    await db_session.commit()

    # reserved_by is NULL on that row → a losing reserve returns None (≠ notif).
    holder = await gating.reserve_type_slot(
        db_session, "ty", "n_X", now, now - timedelta(minutes=30), test=False,
    )
    assert holder != "n_X"
