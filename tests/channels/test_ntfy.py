"""ntfy native channel (app/channels/ntfy.py) and the generic provider_ref."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.channels import ntfy as ntfy_mod
from app.channels.base import Notification
from app.channels.ntfy import NtfyChannel, build_message
from app.channels.registry import REGISTRY
from app.core.channel_actions import record_provider_reference
from app.db.models import Delivery


def _notif(**kw):
    base = dict(id="ntf_1", type="disk_full", severity="critical", icon="💾", title="Disk full ăîș",
                message="95 %", fired_at=datetime.now(UTC), vars_payload={}, rule_id=None)
    base.update(kw)
    return Notification(**base)


def test_registered():
    assert REGISTRY["ntfy"] is NtfyChannel


def test_build_message_maps_priority_tags_and_links():
    body = build_message(_notif(), {"topic": "home", "tags": ["solar"], "admin_url": "https://alerts.example.com/"})
    assert body["topic"] == "home"
    assert body["title"] == "💾 Disk full ăîș", "UTF-8 title, icon first"
    assert body["priority"] == 5 and body["tags"] == ["critical", "solar"]
    assert body["click"] == "https://alerts.example.com/admin/#/log?id=ntf_1"
    assert body["actions"][0]["action"] == "view"
    info = build_message(_notif(severity="info", icon=None, message=None), {"topic": "t", "priority_map": {"info": 9}})
    assert info["priority"] == 5, "clamped to 1–5"
    assert info["message"] == "Disk full ăîș", "falls back to the title"
    assert "click" not in info


class _Resp(SimpleNamespace):
    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class _Calls(list):
    response: list


@pytest.fixture
def calls(monkeypatch):
    seen = _Calls()
    seen.response = [_Resp(status_code=200, payload={"id": "abc123", "event": "message"}, text="")]

    async def fake(method, url, **kw):
        seen.append({"method": method, "url": url, **kw})
        return seen.response[0]

    monkeypatch.setattr(ntfy_mod, "safe_request", fake)
    return seen


async def test_send_success_reports_provider_ref(calls):
    res = await NtfyChannel().send(_notif(), {"server_url": "https://ntfy.example/", "topic": "t", "token": "tk"})
    assert res.ok and res.response["provider_ref"] == "ntfy:abc123"
    sent = calls[0]
    assert sent["url"] == "https://ntfy.example" and sent["json"]["topic"] == "t"
    assert sent["headers"]["Authorization"] == "Bearer tk"


async def test_send_failures(calls, monkeypatch):
    assert not (await NtfyChannel().send(_notif(), {})).ok
    calls.response[0] = _Resp(status_code=403, payload={}, text="forbidden")
    res = await NtfyChannel().send(_notif(), {"topic": "t"})
    assert not res.ok and "403" in res.error

    async def boom(*a, **k):
        raise httpx.ConnectTimeout("slow")
    monkeypatch.setattr(ntfy_mod, "safe_request", boom)
    res = await NtfyChannel().send(_notif(), {"topic": "t"})
    assert not res.ok and res.error == "ntfy timeout"


async def test_provider_ref_recorded_on_delivery(db_session):
    d = Delivery(notification_id="ntf_x", channel="phone", state="pending", attempts=0, idempotency_key="k")
    await record_provider_reference(db_session, d, {"status": 200, "provider_ref": "ntfy:abc123"})
    assert d.provider_ref == "ntfy:abc123"
    await record_provider_reference(db_session, d, {"status": 200})
    assert d.provider_ref == "ntfy:abc123", "a response without a ref changes nothing"


async def test_ntfy_meets_the_adapter_contract(monkeypatch):
    from tests.channels._kit import FakeHTTP, assert_http_contract, reply
    http = FakeHTTP.install(monkeypatch, ntfy_mod)
    await assert_http_contract(NtfyChannel(), {"topic": "t", "token": "tk_s3cret"}, http,
                               secrets=["tk_s3cret"], ok_reply=reply(200, {"id": "m1"}))
