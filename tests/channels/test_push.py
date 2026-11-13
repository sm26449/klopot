"""PushChannel tests with mocked pywebpush."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.channels.base import Notification
from app.channels.push import PushChannel
from app.db.models import UserPref


def _notif():
    return Notification(
        id="ntf_test", type="t", severity="warning", icon="⚠️",
        title="Hot", message="60C",
        fired_at=datetime(2026, 5, 10, 12, 0, 0),
    )


def _config(**overrides):
    base = {
        "vapid_public": "PUB",
        "vapid_private": "PRIV",
        "vapid_subject": "mailto:ops@x",
        "ttl_sec": 3600,
    }
    base.update(overrides)
    return base


# ── Config validation ────────────────────────────────────────────


async def test_missing_vapid_public(db_engine):
    r = await PushChannel().send(_notif(), {
        "vapid_private": "p", "vapid_subject": "mailto:x",
    })
    assert r.ok is False
    assert "vapid" in r.error


async def test_missing_subject(db_engine):
    r = await PushChannel().send(_notif(), {
        "vapid_public": "p", "vapid_private": "p",
    })
    assert r.ok is False


# ── No subscriptions = ok ────────────────────────────────────────


async def test_no_subscriptions_returns_ok(db_engine):
    """Empty fan-out is not a failure."""
    r = await PushChannel().send(_notif(), _config())
    assert r.ok is True
    assert r.response["delivered"] == 0
    assert r.response["subscriptions"] == 0


async def test_subject_alias_accepted(db_engine):
    """F34: the UI emitted `subject`; the adapter must accept it as an alias
    for `vapid_subject` instead of failing 'missing subject'."""
    r = await PushChannel().send(_notif(), {
        "vapid_public": "p", "vapid_private": "p", "subject": "mailto:ops@x",
    })
    # No "missing subject" error — it proceeds to the (empty) fan-out.
    assert r.ok is True
    assert r.response["subscriptions"] == 0


# ── Successful delivery ──────────────────────────────────────────


async def test_delivery_to_one_subscription(db_engine, db_session):
    db_session.add(UserPref(
        user_id="user1",
        settings={
            "push_subscriptions": [
                {"endpoint": "https://fcm.example/abc",
                 "keys": {"p256dh": "k", "auth": "a"}},
            ],
        },
    ))
    await db_session.commit()

    fake_webpush = MagicMock()
    with patch("pywebpush.webpush", fake_webpush), \
         patch("pywebpush.WebPushException", Exception):
        r = await PushChannel().send(_notif(), _config())

    assert r.ok is True
    assert r.response["delivered"] == 1
    assert r.response["subscriptions"] == 1
    fake_webpush.assert_called_once()


async def test_payload_includes_notif_fields(db_engine, db_session):
    db_session.add(UserPref(
        user_id="u",
        settings={"push_subscriptions": [
            {"endpoint": "https://x", "keys": {"p256dh": "k", "auth": "a"}},
        ]},
    ))
    await db_session.commit()

    fake_webpush = MagicMock()
    with patch("pywebpush.webpush", fake_webpush), \
         patch("pywebpush.WebPushException", Exception):
        await PushChannel().send(_notif(), _config())

    import json as _j

    payload = _j.loads(fake_webpush.call_args.kwargs["data"])
    assert payload["title"] == "Hot"
    assert payload["severity"] == "warning"
    assert payload["tag"] == "t"


async def test_multi_subscriptions_all_attempted(db_engine, db_session):
    db_session.add(UserPref(
        user_id="ua",
        settings={"push_subscriptions": [
            {"endpoint": f"https://x/{i}", "keys": {"p256dh": "k", "auth": "a"}}
            for i in range(3)
        ]},
    ))
    await db_session.commit()

    fake_webpush = MagicMock()
    with patch("pywebpush.webpush", fake_webpush), \
         patch("pywebpush.WebPushException", Exception):
        r = await PushChannel().send(_notif(), _config())

    assert fake_webpush.call_count == 3
    assert r.response["delivered"] == 3


# ── Failure handling ─────────────────────────────────────────────


async def test_410_subscription_marked_stale(db_engine, db_session):
    """410 Gone means the subscription has expired — should be removed
    from user_prefs."""
    from sqlalchemy import select

    class FakeWebPushException(Exception):
        pass

    db_session.add(UserPref(
        user_id="ub",
        settings={"push_subscriptions": [
            {"endpoint": "https://fcm/expired",
             "keys": {"p256dh": "k", "auth": "a"}},
            {"endpoint": "https://fcm/valid",
             "keys": {"p256dh": "k", "auth": "a"}},
        ]},
    ))
    await db_session.commit()

    def fake_webpush(*, subscription_info, **kw):
        if "expired" in subscription_info["endpoint"]:
            raise FakeWebPushException("Push failed: 410 Gone")
        return None

    with patch("pywebpush.webpush", fake_webpush), \
         patch("pywebpush.WebPushException", FakeWebPushException):
        r = await PushChannel().send(_notif(), _config())

    # Channel reports ok because at least one delivered
    assert r.ok is True
    # Stale endpoint removed
    pref = (
        await db_session.execute(select(UserPref).where(UserPref.user_id == "ub"))
    ).scalar_one()
    await db_session.refresh(pref)
    eps = [s["endpoint"] for s in pref.settings["push_subscriptions"]]
    assert "https://fcm/expired" not in eps
    assert "https://fcm/valid" in eps


async def test_all_subscriptions_failing_returns_error(db_engine, db_session):
    class FakeWebPushException(Exception):
        pass

    db_session.add(UserPref(
        user_id="uc",
        settings={"push_subscriptions": [
            {"endpoint": "https://x", "keys": {"p256dh": "k", "auth": "a"}},
        ]},
    ))
    await db_session.commit()

    def fake_webpush(**kw):
        raise FakeWebPushException("Push failed: 500")

    with patch("pywebpush.webpush", fake_webpush), \
         patch("pywebpush.WebPushException", FakeWebPushException):
        r = await PushChannel().send(_notif(), _config())

    assert r.ok is False
    assert "500" in r.error


# ── Healthcheck ──────────────────────────────────────────────────


async def test_healthcheck_reports_lib_installed():
    h = await PushChannel().healthcheck({})
    assert "lib_installed" in h
    assert "reachable" in h
