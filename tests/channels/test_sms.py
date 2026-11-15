"""SMSChannel: providers http / twilio / teltonika, and the pre-0031 config.

The channel sends through safe_request (SSRF-safe, IP-pinned transport —
audit S-05), so these mock safe_request, not httpx."""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.base import Notification
from app.channels.sms import SMSChannel
from app.channels.sms_config import upgrade_legacy, validate_config
from app.utils.safe_http import EgressBlocked


def _notif(title="t", message="m"):
    return Notification(
        id="ntf_test", type="t", severity="warning", icon=None,
        title=title, message=message, fired_at=datetime(2026, 5, 10, 12, 0, 0),
    )


def _resp(*, status: int = 200, body: dict | None = None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body if body is not None else {"sent": True}
    r.text = "stub"
    return r


def _patch_send(*responses, status: int = 200, body: dict | None = None):
    """Patch safe_request; returns (patcher, mock)."""
    mock = AsyncMock(side_effect=list(responses)) if responses else AsyncMock(return_value=_resp(status=status, body=body))
    return patch("app.channels.sms.safe_request", mock), mock


HTTP = {"provider": "http", "url": "http://gw/send", "phone": "+40700"}


# ── Compatibility: a gateway configured before 0031 keeps the same request ──


async def test_legacy_gateway_config_sends_the_same_request_as_before():
    """Old shape → upgraded → POST <gateway>/api/sms/send, X-API-Key, and a JSON
    body equal to the old {"phone", "message"} (text = title\\nmessage)."""
    legacy = {"gateway_url": "http://gateway:5080/", "phone": "+40700000000",
              "gateway_api_key": "k3y"}
    patcher, mock = _patch_send()
    with patcher:
        r = await SMSChannel().send(_notif(title="Baterie descărcată", message='SOC "18"%'), upgrade_legacy(legacy))
    assert r.ok is True
    method, url = mock.call_args.args
    assert (method, url) == ("POST", "http://gateway:5080/api/sms/send")
    headers = mock.call_args.kwargs["headers"]
    assert headers["X-API-Key"] == "k3y" and headers["Content-Type"] == "application/json"
    assert json.loads(mock.call_args.kwargs["content"]) == {
        "phone": "+40700000000", "message": 'Baterie descărcată\nSOC "18"%'}


def test_upgrade_legacy_maps_every_field_and_keeps_refs():
    out = upgrade_legacy({"gateway_url": "http://gw:5080", "phone": "+1", "gateway_api_key_ref": "SMS_KEY"})
    assert out == {
        "phone": "+1", "provider": "http", "url": "http://gw:5080/api/sms/send", "method": "POST",
        "content_type": "application/json",
        "body_template": '{"phone": "{phone | jsonstr}", "message": "{text | jsonstr}"}',
        "health_url": "http://gw:5080/api/health",
        "auth_kind": "header", "auth_header": "X-API-Key", "auth_value_ref": "SMS_KEY",
    }
    assert upgrade_legacy(HTTP) is HTTP  # already new → untouched


def test_migration_0031_rewrite_matches_the_app():
    """The migration carries its own copy of the rewrite; keep them equal."""
    import importlib.util
    import pathlib

    path = next(pathlib.Path("alembic/versions").glob("*_0031_sms_providers.py"))
    spec = importlib.util.spec_from_file_location("m0031", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for cfg in ({"gateway_url": "http://gw", "phone": "+1"},
                {"gateway_url": "http://gw/", "phone": "+1", "gateway_api_key": "x"},
                {"gateway_url": "http://gw", "phone": "+1", "gateway_api_key_ref": "R"}):
        assert mod._upgrade_config(cfg) == upgrade_legacy(cfg)
    assert mod._upgrade_config(HTTP) is None


# ── http provider ──────────────────────────────────────────────────


async def test_http_custom_body_and_bearer_auth():
    cfg = {**HTTP, "content_type": "application/x-www-form-urlencoded",
           "body_template": "to={phone}&msg={text}&sev={severity}", "auth_kind": "bearer", "auth_value": "tok"}
    patcher, mock = _patch_send()
    with patcher:
        r = await SMSChannel().send(_notif(title="A", message="B"), cfg)
    assert r.ok
    assert mock.call_args.kwargs["content"] == "to=+40700&msg=A\nB&sev=warning"
    assert mock.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"


async def test_several_recipients_each_get_the_message():
    patcher, mock = _patch_send()
    with patcher:
        r = await SMSChannel().send(_notif(), {**HTTP, "phone": "+1, +2 ,+3"})
    assert r.ok and r.response["sent"] == 3
    assert [json.loads(c.kwargs["content"])["phone"] for c in mock.call_args_list] == ["+1", "+2", "+3"]


async def test_truncates_to_max_chars():
    patcher, mock = _patch_send()
    with patcher:
        await SMSChannel().send(_notif(message="x" * 1000), {**HTTP, "max_chars": 160})
    msg = json.loads(mock.call_args.kwargs["content"])["message"]
    assert len(msg) == 160 and msg.endswith("…")


async def test_http_error_status_fails_and_redacts():
    patcher, _ = _patch_send(status=503)
    with patcher:
        r = await SMSChannel().send(_notif(), HTTP)
    assert r.ok is False and "503" in r.error


async def test_invalid_json_body_is_refused_before_sending():
    patcher, mock = _patch_send()
    with patcher:
        r = await SMSChannel().send(_notif(), {**HTTP, "body_template": '{"phone": {phone}'})
    assert r.ok is False and "not valid JSON" in r.error
    mock.assert_not_called()


async def test_timeout_and_blocked_egress():
    with patch("app.channels.sms.safe_request", AsyncMock(side_effect=httpx.TimeoutException("late"))):
        r = await SMSChannel().send(_notif(), HTTP)
    assert r.ok is False and "timeout" in r.error.lower()
    with patch("app.channels.sms.safe_request", AsyncMock(side_effect=EgressBlocked("private address blocked"))):
        r = await SMSChannel().send(_notif(), {**HTTP, "url": "http://169.254.169.254"})
    assert r.ok is False and "blocked" in r.error.lower()


async def test_missing_phone_and_unknown_provider():
    assert "phone" in (await SMSChannel().send(_notif(), {"provider": "http", "url": "http://gw"})).error
    assert "unknown SMS provider" in (await SMSChannel().send(_notif(), {**HTTP, "provider": "pigeon"})).error


# ── twilio ─────────────────────────────────────────────────────────


async def test_twilio_posts_form_with_basic_auth():
    cfg = {"provider": "twilio", "phone": "+40700", "account_sid": "AC1", "auth_token": "tk", "from_number": "+1555"}
    patcher, mock = _patch_send(status=201, body={"sid": "SM9", "status": "queued"})
    with patcher:
        r = await SMSChannel().send(_notif(title="A", message="B"), cfg)
    assert r.ok and r.response["responses"][0] == {"sid": "SM9", "status": "queued"}
    assert mock.call_args.args[1] == "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages.json"
    assert mock.call_args.kwargs["data"] == {"To": "+40700", "From": "+1555", "Body": "A\nB"}
    assert mock.call_args.kwargs["headers"]["Authorization"].startswith("Basic ")


# ── teltonika ──────────────────────────────────────────────────────


async def test_teltonika_logs_in_once_then_sends_to_each_number():
    cfg = {"provider": "teltonika", "phone": "+1,+2", "router_url": "https://192.0.2.1/",
           "username": "admin", "password": "pw"}
    patcher, mock = _patch_send(
        _resp(body={"success": True, "data": {"token": "T0K"}}), _resp(body={"success": True}), _resp(body={"success": True}))
    with patcher:
        r = await SMSChannel().send(_notif(), cfg)
    assert r.ok and r.response["sent"] == 2
    login, first, _ = mock.call_args_list
    assert login.args[1] == "https://192.0.2.1/api/login" and login.kwargs["json"] == {"username": "admin", "password": "pw"}
    assert first.args[1] == "https://192.0.2.1/api/messages/actions/send"
    assert first.kwargs["json"] == {"data": {"number": "+1", "message": "t\nm", "modem": "1-1"}}
    assert first.kwargs["headers"]["Authorization"] == "Bearer T0K"


async def test_teltonika_login_without_token_fails():
    cfg = {"provider": "teltonika", "phone": "+1", "router_url": "https://r", "username": "a", "password": "p"}
    patcher, _ = _patch_send(body={"success": False})
    with patcher:
        r = await SMSChannel().send(_notif(), cfg)
    assert r.ok is False and "token" in r.error


# ── healthcheck + validation ───────────────────────────────────────


async def test_healthcheck_uses_health_url():
    patcher, mock = _patch_send(status=200)
    with patcher:
        h = await SMSChannel().healthcheck({**HTTP, "health_url": "http://gw/api/health"})
    assert h["reachable"] is True and mock.call_args.args == ("GET", "http://gw/api/health")
    assert (await SMSChannel().healthcheck(HTTP))["reachable"] is None  # nothing to probe


@pytest.mark.parametrize(("cfg", "missing"), [
    ({"provider": "http", "phone": "+1"}, "url"),
    ({"provider": "twilio", "phone": "+1", "account_sid": "A"}, "from_number"),
    ({"provider": "twilio", "phone": "+1", "account_sid": "A", "from_number": "+2"}, "auth_token"),
    ({"provider": "teltonika", "router_url": "https://r", "username": "u", "password_ref": "P"}, "phone"),
])
def test_validate_config_names_what_is_missing(cfg, missing):
    with pytest.raises(ValueError, match=missing):
        validate_config(cfg)


def test_validate_config_accepts_refs_and_skips_secrets_for_exports():
    validate_config({"provider": "twilio", "phone": "+1", "account_sid": "A", "from_number": "+2", "auth_token_ref": "T"})
    validate_config({"provider": "twilio", "phone": "+1", "account_sid": "A", "from_number": "+2"}, require_secrets=False)


async def test_a_failed_healthcheck_does_not_return_the_url():
    """Pre-open-source audit: the healthcheck stored str(e), and httpx quotes
    the URL — a health URL with ?token= reached read-scoped keys."""
    leaky = httpx.ConnectError("connect failed: http://gw/api/health?token=s3cr3t-value")
    patcher, _ = _patch_send(leaky)
    with patcher:
        h = await SMSChannel().healthcheck({**HTTP, "health_url": "http://gw/api/health?token=s3cr3t-value"})
    assert h["reachable"] is False
    assert "s3cr3t-value" not in h["error"]
