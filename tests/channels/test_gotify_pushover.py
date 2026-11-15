"""Gotify and Pushover channels — the adapter kit plus each one's specifics."""
from __future__ import annotations

from app.channels import gotify as gotify_mod
from app.channels import pushover as pushover_mod
from app.channels.gotify import GotifyChannel
from app.channels.pushover import PushoverChannel, build_form, receipt_of
from app.channels.registry import REGISTRY
from app.meta_kinds import describe_kinds
from tests.channels._kit import FakeHTTP, assert_http_contract, notification, reply

GOTIFY = {"server_url": "https://gotify.example/", "app_token": "gtk_s3cret", "admin_url": "https://alerts.example"}
PUSHOVER = {"user_key": "usr_s3cretkey", "app_token": "app_s3crettok"}


def test_registered_and_described():
    assert REGISTRY["gotify"] is GotifyChannel
    assert REGISTRY["pushover"] is PushoverChannel
    kinds = describe_kinds()["channels"]
    assert kinds["pushover"]["intrusive"] is True
    assert kinds["sms"]["intrusive"] is True
    assert kinds["gotify"]["intrusive"] is False
    secret = {f["name"] for f in kinds["pushover"]["fields"] if f["secret"]}
    assert secret == {"app_token", "user_key"}


# ── Gotify ──────────────────────────────────────────────────────────

async def test_gotify_contract(monkeypatch):
    http = FakeHTTP.install(monkeypatch, gotify_mod)
    await assert_http_contract(GotifyChannel(), GOTIFY, http, secrets=["gtk_s3cret"], ok_reply=reply(200, {"id": 7}))


async def test_gotify_request(monkeypatch):
    http = FakeHTTP.install(monkeypatch, gotify_mod).will(reply(200, {"id": 42}))
    res = await GotifyChannel().send(notification(), GOTIFY)
    assert res.response["provider_ref"] == "gotify:42"
    call = http.calls[0]
    assert call["url"] == "https://gotify.example/message"
    assert call["headers"]["X-Gotify-Key"] == "gtk_s3cret"
    assert "gtk_s3cret" not in call["url"], "token never in the URL"
    body = call["json"]
    assert body["priority"] == 8
    assert body["title"] == "🧪 Kit title ăîș"
    assert body["extras"]["client::notification"]["click"]["url"] == "https://alerts.example/admin/#/log?id=ntf_kit_1"
    assert not (await GotifyChannel().send(notification(), {"server_url": "https://g"})).ok   # no token


# ── Pushover ────────────────────────────────────────────────────────

async def test_pushover_contract(monkeypatch):
    http = FakeHTTP.install(monkeypatch, pushover_mod)
    await assert_http_contract(PushoverChannel(), PUSHOVER, http, secrets=["usr_s3cretkey", "app_s3crettok"],
                               ok_reply=reply(200, {"status": 1, "request": "r1"}))


def test_pushover_priorities_and_emergency_opt_in():
    info = build_form(notification(severity="info"), {}, "t", "u")
    assert info["priority"] == "-1" and "retry" not in info
    crit = build_form(notification(severity="critical"), {}, "t", "u")
    assert crit["priority"] == "1", "no emergency unless asked for"
    emergency = build_form(notification(severity="critical"),
                           {"emergency_for": ["critical"], "retry_sec": 5, "expire_sec": 99999}, "t", "u")
    assert emergency["priority"] == "2"
    assert emergency["retry"] == "30", "Pushover's minimum retry"
    assert emergency["expire"] == "10800", "Pushover's maximum expire"
    linked = build_form(notification(), {"admin_url": "https://a.example/"}, "t", "u")
    assert linked["url"] == "https://a.example/admin/#/log?id=ntf_kit_1"


async def test_pushover_refs_and_api_errors(monkeypatch):
    http = FakeHTTP.install(monkeypatch, pushover_mod).will(reply(200, {"status": 1, "request": "req9", "receipt": "rcpt9"}))
    res = await PushoverChannel().send(notification(), {**PUSHOVER, "emergency_for": ["critical"]})
    assert res.response["provider_ref"] == "pushover:receipt:rcpt9"
    assert receipt_of(res.response["provider_ref"]) == "rcpt9"
    assert receipt_of("pushover:req9") is None
    assert http.calls[0]["data"]["priority"] == "2"

    http.will(reply(400, {"status": 0, "errors": ["user identifier is invalid"]}))
    res = await PushoverChannel().send(notification(), PUSHOVER)
    assert not res.ok
    assert "user identifier is invalid" in res.error
    assert "usr_s3cretkey" not in res.error


def test_test_notifications_open_the_channels_page_real_alerts_their_log_entry():
    """A channel test has no log entry, so its tap target is the Channels page."""
    from datetime import datetime

    from app.channels.base import CHANNEL_TEST_TYPE, Notification, admin_link

    def n(type_):
        return Notification(id="ntf_1", type=type_, severity="info", icon=None, title="t", message="m",
                            fired_at=datetime(2026, 11, 14))
    cfg = {"admin_url": "https://alerts.example.com/"}
    assert admin_link(cfg, n("disk_full")) == "https://alerts.example.com/admin/#/log?id=ntf_1"
    assert admin_link(cfg, n(CHANNEL_TEST_TYPE)) == "https://alerts.example.com/admin/#/channels"
    assert admin_link({}, n("disk_full")) is None
