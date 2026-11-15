"""Web Push channel (docs/WEB_PUSH.md): allowlist, payload, VAPID, end-to-end
encryption, per-device outcomes (404/410 removal, 429 deferral, failure streak)."""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import select

from app.channels import push
from app.channels.base import CHANNEL_TEST_TYPE, Notification
from app.channels.push import PushChannel
from app.db.models import PushSubscription, Severity, SystemEvent


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


VAPID_KEY = ec.generate_private_key(ec.SECP256R1())
VAPID_PRIVATE = _b64(VAPID_KEY.private_numbers().private_value.to_bytes(32, "big"))
VAPID_PUBLIC = _b64(VAPID_KEY.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))


class Device:
    """A browser: its own key pair + auth secret, so a test can decrypt what it got."""

    def __init__(self, endpoint="https://web.push.apple.com/QGuQyavXutnMH"):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.endpoint = endpoint

    def row(self, **kw) -> PushSubscription:
        return PushSubscription(
            endpoint=self.endpoint, endpoint_hash=push.endpoint_hash(self.endpoint),
            p256dh=_b64(self.key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)),
            auth=_b64(self.auth), label=kw.pop("label", "iPhone · Safari"), **kw)

    def decrypt(self, body: bytes) -> dict:
        import http_ece

        return json.loads(http_ece.decrypt(body, private_key=self.key, auth_secret=self.auth, version="aes128gcm"))


def _notif(severity="warning", type_="disk_full", message="Disk at 95%"):
    return Notification(id="ntf_1", type=type_, severity=severity, icon="💾", title="Disk full",
                        message=message, fired_at=datetime(2026, 11, 15, 12, 0, 0))


CONFIG = {"vapid_private": VAPID_PRIVATE, "vapid_subject": "mailto:ops@example.com"}


def _resp(status=201, headers=None, text=""):
    return MagicMock(status_code=status, headers=headers or {}, text=text)


# ── Pure helpers ──────────────────────────────────────────────────


@pytest.mark.parametrize(("url", "ok"), [
    ("https://web.push.apple.com/abc", True),
    ("https://fcm.googleapis.com/fcm/send/abc", True),
    ("https://updates.push.services.mozilla.com/wpush/v2/abc", True),
    ("https://wns2-par02p.notify.windows.com/w/?token=abc", True),
    ("http://fcm.googleapis.com/fcm/send/abc", False),              # not https
    ("https://evil.example.com/abc", False),
    ("https://fcm.googleapis.com.evil.com/x", False),
    ("https://push.apple.com/x", False),                             # *.push.apple.com needs a subdomain
    ("https://user:pw@fcm.googleapis.com/x", False),
    ("https://127.0.0.1/x", False),
])
def test_endpoint_allowlist(url, ok):
    assert push.endpoint_allowed(url) is ok


def test_extra_hosts_extend_the_allowlist():
    assert push.endpoint_allowed("https://push.example.org/x", ["push.example.org"])
    assert not push.endpoint_allowed("https://a.push.example.org/x", ["push.example.org"])
    assert push.endpoint_allowed("https://a.push.example.org/x", ["*.push.example.org"])


def test_severity_filter():
    assert push.reaches("warning", "critical") and push.reaches("warning", "warning")
    assert not push.reaches("warning", "info") and not push.reaches("critical", "warning")
    assert push.reaches("info", "info")


def test_payload_is_trimmed_to_fit_and_keeps_the_link():
    raw = push.build_payload(_notif(message="ă" * 5000))
    data = json.loads(raw)
    assert len(raw) <= push.MAX_PAYLOAD_BYTES and data["body"].endswith("…")
    assert data["url"] == "/admin/#/log?id=ntf_1" and data["tag"] == "disk_full" and data["title"] == "💾 Disk full"
    test = json.loads(push.build_payload(_notif(type_=CHANNEL_TEST_TYPE)))
    assert test["url"] == "/admin/#/account"


def test_topic_is_short_and_url_safe():
    t = push.topic_for("a" * 200)
    assert len(t) <= 32 and all(c.isalnum() or c in "-_" for c in t)


def test_public_key_is_derived_from_the_private_key():
    assert push.vapid_public_key(VAPID_PRIVATE) == VAPID_PUBLIC


@pytest.mark.parametrize(("config", "why"), [
    ({"vapid_subject": "mailto:x@y"}, "not set"),
    ({"vapid_private": VAPID_PRIVATE}, "mailto"),
    ({"vapid_private": VAPID_PRIVATE, "vapid_subject": "ops@example.com"}, "mailto"),
    ({"vapid_private": "not-a-key", "vapid_subject": "mailto:x@y"}, "not valid"),
])
def test_vapid_identity_explains_what_is_missing(config, why):
    identity, reason = push.vapid_identity(config)
    assert identity is None and why in reason


# ── Sending ───────────────────────────────────────────────────────


async def test_no_devices_is_not_a_failure(db_engine):
    r = await PushChannel().send(_notif(), CONFIG)
    assert r.ok is True and r.response == {"devices": 0, "delivered": 0}


async def test_bad_vapid_config_fails_permanently(db_engine):
    r = await PushChannel().send(_notif(), {"vapid_subject": "mailto:x@y"})
    assert r.ok is False and r.permanent is True


async def test_delivery_is_encrypted_signed_and_through_safe_request(db_engine, db_session):
    dev = Device()
    db_session.add(dev.row())
    await db_session.commit()
    sent = AsyncMock(return_value=_resp(201))
    with patch("app.channels.push.safe_request", sent):
        r = await PushChannel().send(_notif(severity="critical"), CONFIG)
    assert r.ok and r.response["delivered"] == 1
    method, url = sent.call_args.args
    kw = sent.call_args.kwargs
    assert (method, url) == ("POST", dev.endpoint)
    h = kw["headers"]
    assert h["Urgency"] == "high" and h["TTL"] == "86400" and h["Content-Encoding"] == "aes128gcm"
    assert h["Topic"] == push.topic_for("disk_full")
    assert h["Authorization"].startswith("vapid t=") and f"k={VAPID_PUBLIC}" in h["Authorization"]
    jwt_payload = json.loads(_unb64(h["Authorization"].split("t=")[1].split(",")[0].split(".")[1]))
    assert jwt_payload["aud"] == "https://web.push.apple.com" and jwt_payload["sub"] == "mailto:ops@example.com"
    # Only the device can read it.
    assert b"Disk" not in kw["content"]
    assert dev.decrypt(kw["content"])["body"] == "Disk at 95%"
    row = (await db_session.execute(select(PushSubscription))).scalar_one()
    await db_session.refresh(row)
    assert row.last_success_at is not None and row.consecutive_failures == 0


async def test_min_severity_filters_devices(db_engine, db_session):
    loud, quiet = Device("https://web.push.apple.com/a"), Device("https://fcm.googleapis.com/fcm/send/b")
    db_session.add_all([loud.row(min_severity=Severity.info), quiet.row(min_severity=Severity.critical)])
    await db_session.commit()
    sent = AsyncMock(return_value=_resp(201))
    with patch("app.channels.push.safe_request", sent):
        r = await PushChannel().send(_notif(severity="warning"), CONFIG)
    assert r.response["devices"] == 1 and sent.call_args.args[1] == loud.endpoint


async def test_a_channel_test_reaches_every_enabled_device(db_engine, db_session):
    a, b = Device("https://web.push.apple.com/a"), Device("https://fcm.googleapis.com/fcm/send/b")
    db_session.add_all([a.row(min_severity=Severity.critical), b.row(enabled=False)])
    await db_session.commit()
    sent = AsyncMock(return_value=_resp(201))
    with patch("app.channels.push.safe_request", sent):
        r = await PushChannel().send(_notif(severity="info", type_=CHANNEL_TEST_TYPE), CONFIG)
    assert r.response["devices"] == 1 and "Topic" not in sent.call_args.kwargs["headers"]


async def test_gone_device_is_removed_with_an_event(db_engine, db_session):
    from app.core.activity import get_activity_writer

    db_session.add(Device().row())
    await db_session.commit()
    with patch("app.channels.push.safe_request", AsyncMock(return_value=_resp(410))):
        r = await PushChannel().send(_notif(), CONFIG)
    assert r.ok is True and r.response["results"][0]["removed"] is True
    await get_activity_writer().flush()
    from tests._db import fresh
    await fresh(db_session)
    assert (await db_session.execute(select(PushSubscription))).scalars().all() == []
    assert [e.event for e in (await db_session.execute(select(SystemEvent))).scalars()] == ["device_removed"]


async def test_rate_limited_everywhere_defers(db_engine, db_session):
    db_session.add(Device().row())
    await db_session.commit()
    with patch("app.channels.push.safe_request", AsyncMock(return_value=_resp(429, {"retry-after": "120"}))):
        r = await PushChannel().send(_notif(), CONFIG)
    assert r.ok is False and r.retry_after == 120


async def test_one_device_down_is_still_a_success(db_engine, db_session):
    db_session.add_all([Device("https://web.push.apple.com/a").row(), Device("https://fcm.googleapis.com/fcm/send/b").row()])
    await db_session.commit()

    async def answer(method, url, **kw):
        return _resp(201) if "apple" in url else _resp(500, text="boom")

    with patch("app.channels.push.safe_request", AsyncMock(side_effect=answer)):
        r = await PushChannel().send(_notif(), CONFIG)
    assert r.ok is True and r.response["delivered"] == 1
    from tests._db import fresh
    await fresh(db_session)
    bad = (await db_session.execute(select(PushSubscription).where(PushSubscription.endpoint.like("%fcm%")))).scalar_one()
    assert bad.consecutive_failures == 1 and "HTTP 500" in bad.last_error


async def test_a_device_is_paused_after_repeated_failures(db_engine, db_session):
    db_session.add(Device().row(consecutive_failures=push.DISABLE_AFTER_FAILURES - 1))
    await db_session.commit()
    with patch("app.channels.push.safe_request", AsyncMock(return_value=_resp(500))):
        r = await PushChannel().send(_notif(), CONFIG)
    assert r.ok is False
    from tests._db import fresh
    await fresh(db_session)
    assert (await db_session.execute(select(PushSubscription))).scalar_one().enabled is False


async def test_an_endpoint_outside_the_allowlist_is_never_called(db_engine, db_session):
    dev = Device("https://evil.example.com/x")
    db_session.add(dev.row())
    await db_session.commit()
    sent = AsyncMock()
    with patch("app.channels.push.safe_request", sent):
        r = await PushChannel().send(_notif(), CONFIG)
    assert r.ok is False and "allowed push service" in r.error and not sent.called


# ── An outage on our side is not the device's fault (audit P04) ──────────────


async def test_internet_outage_does_not_pause_devices(db_engine, db_session):
    import httpx

    from tests._db import fresh

    db_session.add_all([Device("https://web.push.apple.com/a").row(),
                        Device("https://fcm.googleapis.com/fcm/send/b").row()])
    await db_session.commit()
    # The host loses its uplink: every send dies before reaching the push service.
    down = AsyncMock(side_effect=httpx.ConnectError("Network is unreachable"))
    with patch("app.channels.push.safe_request", down):
        for _ in range(push.DISABLE_AFTER_FAILURES + 5):
            r = await PushChannel().send(_notif(severity="critical"), CONFIG)
            assert r.ok is False
            assert r.permanent is False   # still worth a retry
    await fresh(db_session)
    devices = (await db_session.execute(select(PushSubscription))).scalars().all()
    assert [d.enabled for d in devices] == [True, True]
    assert [d.consecutive_failures for d in devices] == [0, 0]
    assert all("ConnectError" in d.last_error for d in devices)   # still shown on the device
    # The uplink is back: the alert reaches both.
    sent = AsyncMock(return_value=_resp(201))
    with patch("app.channels.push.safe_request", sent):
        r = await PushChannel().send(_notif(severity="critical"), CONFIG)
    assert r.ok is True
    assert sent.await_count == 2


@pytest.mark.parametrize("failure", ["timeout", "dns"])
async def test_timeouts_and_unresolvable_names_do_not_count(db_engine, db_session, failure):
    import httpx

    from app.utils.safe_http import EgressBlocked
    from tests._db import fresh

    db_session.add(Device().row(consecutive_failures=push.DISABLE_AFTER_FAILURES - 1))
    await db_session.commit()
    exc = httpx.ReadTimeout("slow") if failure == "timeout" else EgressBlocked("DNS resolution failed")
    with patch("app.channels.push.safe_request", AsyncMock(side_effect=exc)):
        assert (await PushChannel().send(_notif(), CONFIG)).ok is False
    await fresh(db_session)
    row = (await db_session.execute(select(PushSubscription))).scalar_one()
    assert row.enabled is True
    assert row.consecutive_failures == push.DISABLE_AFTER_FAILURES - 1


async def test_only_auto_paused_devices_is_a_failure_not_sent(db_engine, db_session):
    db_session.add(Device().row(enabled=False, consecutive_failures=push.DISABLE_AFTER_FAILURES,
                                paused_reason=push.PAUSED_BY_SERVICE))
    await db_session.commit()
    sent = AsyncMock()
    with patch("app.channels.push.safe_request", sent):
        r = await PushChannel().send(_notif(severity="critical"), CONFIG)
    assert r.ok is False
    assert r.permanent is True
    assert "paused" in r.error
    assert r.response == {"devices": 0, "delivered": 0, "paused": 1}
    sent.assert_not_awaited()


async def test_a_device_the_operator_paused_is_not_a_failure(db_engine, db_session):
    db_session.add(Device().row(enabled=False, consecutive_failures=0))
    await db_session.commit()
    r = await PushChannel().send(_notif(severity="critical"), CONFIG)
    assert r.ok is True
    assert r.response == {"devices": 0, "delivered": 0}


async def test_an_auto_paused_device_below_the_alert_severity_is_not_a_failure(db_engine, db_session):
    db_session.add(Device().row(enabled=False, consecutive_failures=push.DISABLE_AFTER_FAILURES,
                                min_severity=Severity.critical, paused_reason=push.PAUSED_BY_SERVICE))
    await db_session.commit()
    r = await PushChannel().send(_notif(severity="warning"), CONFIG)
    assert r.ok is True
