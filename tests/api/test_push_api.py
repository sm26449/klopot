"""``/v1/push`` (docs/WEB_PUSH.md): config, a browser registers itself,
admins manage devices, a test reaches one device and is an Activity attempt."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app import auth as auth_module
from app.auth import CSRF_HEADER
from app.core.activity import get_activity_writer
from app.core.passwords import hash_password
from app.db.models import AdminUser, AuditLog, DeliveryAttempt, PushSubscription
from tests.channels.test_push import VAPID_PRIVATE, VAPID_PUBLIC, Device

PASSWORD = "correct-horse-battery-staple"
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1")


@pytest.fixture(autouse=True)
def _clean_session_cache():
    auth_module.invalidate_session_cache()
    yield
    auth_module.invalidate_session_cache()


@pytest.fixture
async def browser(db_client, db_session):
    db_session.add(AdminUser(id=1, username="admin", password_hash=hash_password(PASSWORD),
                             role="admin", is_active=True, must_change_password=False))
    await db_session.commit()
    r = await db_client.post("/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return db_client, {CSRF_HEADER: r.json()["csrf_token"], "User-Agent": IPHONE_UA}


async def _channel(client, headers, **config):
    r = await client.post("/v1/channels", headers=headers, json={
        "name": "phones", "kind": "push",
        "config": {"vapid_private": VAPID_PRIVATE, "vapid_subject": "mailto:ops@example.com", **config}})
    assert r.status_code == 201, r.text
    return r.json()


def _sub(dev: Device) -> dict:
    row = dev.row()
    return {"endpoint": dev.endpoint, "keys": {"p256dh": row.p256dh, "auth": row.auth}}


async def test_config_says_why_push_is_off_then_gives_the_key(browser):
    client, h = browser
    assert (await client.get("/v1/push/config")).json() == {
        "enabled": False, "public_key": None, "channel": None, "reason": "no_channel"}
    await _channel(client, h)
    cfg = (await client.get("/v1/push/config")).json()
    assert cfg["enabled"] is True and cfg["public_key"] == VAPID_PUBLIC and cfg["channel"] == "phones"


async def test_a_browser_registers_itself_once(browser, db_session):
    client, h = browser
    dev = Device()
    r = await client.post("/v1/push/subscriptions", headers=h, json=_sub(dev))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["label"] == "iPhone · Safari" and body["min_severity"] == "warning" and body["enabled"] is True
    assert body["service"].startswith("web.push.apple.com/…") and dev.endpoint not in str(body)
    # Same endpoint again (keys rotated): the same device, refreshed.
    again = _sub(dev) | {"keys": _sub(Device())["keys"]}
    r2 = await client.post("/v1/push/subscriptions", headers=h, json=again)
    assert r2.status_code == 200 and r2.json()["id"] == body["id"]
    rows = (await db_session.execute(select(PushSubscription))).scalars().all()
    assert len(rows) == 1 and rows[0].p256dh == again["keys"]["p256dh"]
    actions = [a.action for a in (await db_session.execute(select(AuditLog))).scalars()]
    assert actions.count("push_subscription.create") == 1
    assert "p256dh" not in str((await db_session.execute(select(AuditLog.after))).scalars().all())


async def test_registration_is_refused_outside_the_allowlist_and_without_a_session(browser, admin_key):
    client, h = browser
    bad = _sub(Device("https://evil.example.com/x"))
    assert (await client.post("/v1/push/subscriptions", headers=h, json=bad)).status_code == 422
    assert (await client.post("/v1/push/subscriptions", headers=h,
                              json=_sub(Device()) | {"keys": {"p256dh": "x", "auth": "y"}})).status_code == 422
    # An API key is not a device.
    client.cookies.clear()
    r = await client.post("/v1/push/subscriptions", headers={"X-API-Key": admin_key}, json=_sub(Device()))
    assert r.status_code == 403
    # A browser write without the CSRF token is refused like any other.


async def test_registration_needs_the_csrf_token(browser):
    client, h = browser
    r = await client.post("/v1/push/subscriptions", headers={"User-Agent": IPHONE_UA}, json=_sub(Device()))
    assert r.status_code == 403


async def test_admin_renames_filters_pauses_and_removes(browser, db_session):
    client, h = browser
    sid = (await client.post("/v1/push/subscriptions", headers=h, json=_sub(Device()))).json()["id"]
    r = await client.patch(f"/v1/push/subscriptions/{sid}", headers=h,
                           json={"label": " My phone ", "min_severity": "critical", "enabled": False})
    assert r.status_code == 200 and r.json()["label"] == "My phone" and r.json()["min_severity"] == "critical"
    assert r.json()["enabled"] is False
    assert (await client.patch(f"/v1/push/subscriptions/{sid}", headers=h,
                               json={"min_severity": "loud"})).status_code == 422
    listed = (await client.get("/v1/push/subscriptions")).json()
    assert [d["label"] for d in listed] == ["My phone"] and len(listed[0]["endpoint_hash"]) == 64
    assert (await client.delete(f"/v1/push/subscriptions/{sid}", headers=h)).status_code == 204
    assert (await client.delete(f"/v1/push/subscriptions/{sid}", headers=h)).status_code == 404
    actions = sorted(a.action for a in (await db_session.execute(select(AuditLog))).scalars()
                     if a.action.startswith("push_subscription"))
    assert actions == ["push_subscription.create", "push_subscription.delete", "push_subscription.update"]


async def test_read_key_cannot_manage_devices(browser, db_client, admin_key):
    client, h = browser
    sid = (await client.post("/v1/push/subscriptions", headers=h, json=_sub(Device()))).json()["id"]
    read_key = (await client.post("/v1/api_keys", headers=h, json={"name": "viewer", "scopes": ["read"]})).json()["key"]
    client.cookies.clear()
    rk = {"X-API-Key": read_key}
    assert (await client.get("/v1/push/subscriptions", headers=rk)).status_code == 200
    assert (await client.patch(f"/v1/push/subscriptions/{sid}", headers=rk, json={"enabled": False})).status_code == 403
    assert (await client.delete(f"/v1/push/subscriptions/{sid}", headers=rk)).status_code == 403


async def test_test_reaches_one_device_and_is_an_activity_attempt(browser, db_session):
    client, h = browser
    await _channel(client, h)
    target, other = Device("https://web.push.apple.com/a"), Device("https://fcm.googleapis.com/fcm/send/b")
    sid = (await client.post("/v1/push/subscriptions", headers=h, json=_sub(target))).json()["id"]
    await client.post("/v1/push/subscriptions", headers=h, json=_sub(other))
    sent = AsyncMock(return_value=MagicMock(status_code=201, headers={}, text=""))
    with patch("app.channels.push.safe_request", sent):
        r = await client.post(f"/v1/push/subscriptions/{sid}/test", headers=h)
    assert r.json() == {"ok": True, "error": None, "delivered": 1}
    assert sent.call_count == 1 and sent.call_args.args[1] == target.endpoint
    payload = target.decrypt(sent.call_args.kwargs["content"])
    assert payload["url"] == "/admin/#/account" and "iPhone" in payload["body"]
    await get_activity_writer().flush()
    attempt = (await db_session.execute(select(DeliveryAttempt))).scalars().one()
    assert attempt.kind == "test" and attempt.channel == "phones" and attempt.outcome == "sent"


async def test_test_without_a_channel_is_a_conflict(browser):
    client, h = browser
    sid = (await client.post("/v1/push/subscriptions", headers=h, json=_sub(Device()))).json()["id"]
    assert (await client.post(f"/v1/push/subscriptions/{sid}/test", headers=h)).status_code == 409


@pytest.mark.parametrize(("ua", "label"), [
    (IPHONE_UA, "iPhone · Safari"),
    ("Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36",
     "Android · Chrome"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 Edg/130.0",
     "Windows · Edge"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:132.0) Gecko/20100101 Firefox/132.0", "Mac · Firefox"),
    ("", "Browser"),
])
def test_device_label_from_the_user_agent(ua, label):
    from app.api.v1.push import device_label

    assert device_label(ua) == label


async def test_config_names_a_broken_channel_and_why(browser):
    client, h = browser
    await _channel(client, h, vapid_subject="ops@example.com")   # not mailto:/https:
    cfg = (await client.get("/v1/push/config")).json()
    assert cfg["enabled"] is False and cfg["channel"] == "phones" and "mailto" in cfg["reason"]
