"""Test fires: a tag for everyone, a privilege for administrators
(public-exposure review, High: Codex #2 / Claude F1).

`test: true` on /v1/fire used to skip the throttle, the delivery gate, quiet
hours, the duplicate claim and the per-type cooldown for any `fire` key — an
unthrottled pager — and those skips existed only because the throttle state
was shared with real fires. Now:

- `test` marks the fire (is_test) and puts it in its own pool: claims and the
  throttle / cooldown (throttle_state, migration 0040) are kept apart from
  real fires, so a test never coalesces or delays a real alert;
- `override_silencing` — granted by api/v1/fire.py to the admin scope only —
  is what skips the silencing gates.
"""
from __future__ import annotations

from datetime import time
from unittest.mock import patch

import pytest

from app.channels.manager import DispatchOutcome
from app.core import gating
from app.core.dispatcher import FireEnvelope, fire
from app.db.models import ChannelKind, Severity, TemplateChannel

pytestmark = pytest.mark.anyio


@pytest.fixture
async def throttled_template(db_session, make_template, make_channel):
    """A template routed to one channel, min_repeat_min = 30."""
    t = make_template(min_repeat_min=30)
    c = make_channel(kind=ChannelKind.ui)
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(TemplateChannel(template_id=t.id, channel_id=c.id, severity_min=Severity.info, enabled=True))
    await db_session.commit()
    await db_session.refresh(t)
    return t


async def _ok(self, notif, channel_names, session, overrides_by_name=None, effective_by_name=None, **_kw):
    return DispatchOutcome(succeeded=list(channel_names), failed={})


async def _fire(db_session, t, n: int, **kw):
    with patch("app.channels.manager.ChannelManager.dispatch", new=_ok):
        r = await fire(FireEnvelope(type=t.type, context={"n": n}, **kw), db_session)
    await db_session.commit()
    return r


async def test_a_fire_key_test_is_throttled_among_tests(throttled_template, db_session):
    """The pager: repeated test fires with fresh contexts were all sent."""
    first = await _fire(db_session, throttled_template, 1, test=True)
    second = await _fire(db_session, throttled_template, 2, test=True)
    assert first.dispatched is True
    assert second.dispatched is False
    assert second.suppressed_reason == "throttled"


async def test_a_test_never_delays_or_absorbs_a_real_alert(throttled_template, db_session):
    test_fire = await _fire(db_session, throttled_template, 1, test=True)
    real_same_context = await _fire(db_session, throttled_template, 1)
    assert test_fire.dispatched is True
    assert real_same_context.dispatched is True, "not throttled by the test, not coalesced onto it"
    assert real_same_context.id != test_fire.id


async def test_a_real_alert_does_not_silence_tests(throttled_template, db_session):
    real = await _fire(db_session, throttled_template, 1)
    test_fire = await _fire(db_session, throttled_template, 2, test=True)
    assert real.dispatched is True
    assert test_fire.dispatched is True


async def test_an_admin_test_skips_the_gates_and_still_counts_in_the_test_pool(throttled_template, db_session):
    a = await _fire(db_session, throttled_template, 1, test=True, override_silencing=True)
    b = await _fire(db_session, throttled_template, 2, test=True, override_silencing=True)
    assert a.dispatched is True
    assert b.dispatched is True, "an administrator's repeated probes are not throttled"
    keyed = await _fire(db_session, throttled_template, 3, test=True)
    assert keyed.suppressed_reason == "throttled", "…but they count, so a fire key's test right after is"
    real = await _fire(db_session, throttled_template, 4)
    assert real.dispatched is True, "and real alerts are untouched"


async def test_quiet_hours_apply_to_a_test_without_the_privilege(db_session, make_template, make_channel):
    t = make_template(min_repeat_min=0)
    c = make_channel(name="ui", kind=ChannelKind.ui, quiet_hours={"window": "22-07"})
    db_session.add_all([t, c])
    await db_session.commit()
    with patch("app.core.gating._tz_now_time", return_value=time(3, 0)):
        plain = await gating.evaluate(gating.GateInput(template=t, rule_id=None, channel_names=["ui"], test=True),
                                      db_session)
        admin = await gating.evaluate(gating.GateInput(template=t, rule_id=None, channel_names=["ui"], test=True,
                                                       override_silencing=True), db_session)
    assert plain.allowed is False
    assert admin.channels == ["ui"]


def test_the_privilege_exists_only_on_a_test_fire():
    with pytest.raises(ValueError, match="only for a test fire"):
        FireEnvelope(type="t", context={}, override_silencing=True)


async def test_the_api_grants_the_privilege_to_admin_only(db_client, admin_key, monkeypatch):
    from app.core import fire_service

    seen: list[bool] = []

    async def capture(session, **kw):
        seen.append(kw["override_silencing"])
        return await real(session, **kw)

    real = fire_service.fire
    monkeypatch.setattr(fire_service, "fire", capture)
    fire_key = (await db_client.post("/v1/api_keys", headers={"X-API-Key": admin_key},
                                     json={"name": "script", "scopes": ["fire"]})).json()["key"]
    for key in (fire_key, admin_key):
        r = await db_client.post("/v1/fire", headers={"X-API-Key": key}, json={"type": "nope", "test": True})
        assert r.status_code in (200, 202), r.text
    assert seen == [False, True]
