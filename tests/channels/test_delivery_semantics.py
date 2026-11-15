"""Delivery semantics an upstream can ask for (SMS http provider + webhook):
an idempotency key that is stable across retries, Retry-After backpressure
that defers instead of failing, statuses that count as delivered, and 4xx
refusals that are final. Contract: sms-gateway >= 1.7.2 (docs/API.md there)."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.base import Notification, SendResult
from app.channels.manager import ChannelManager
from app.channels.sms import SMSChannel
from app.channels.sms_config import upgrade_legacy, validate_config
from app.channels.webhook import WebhookChannel
from app.core import outbox
from app.db.models import ChannelKind, Delivery, DeliveryState
from app.utils.http_retry import is_permanent_client_error, parse_retry_after


def _notif(**kw):
    return Notification(id=kw.get("id", "ntf_1"), type="disk_full", severity="critical", icon=None,
                        title="Disk full", message="93%", fired_at=datetime(2026, 11, 14, 12, 0))


def _resp(status=200, body=None, headers=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body if body is not None else {"status": "sent"}
    r.text = json.dumps(body or {})
    r.headers = headers or {}
    return r


HTTP = {"provider": "http", "url": "http://gw/api/sms/send", "phone": "+40700000000",
        "body_template": '{"phone": "{phone | jsonstr}", "message": "{text | jsonstr}", '
                         '"idempotency_key": "{idempotency_key | jsonstr}:{phone | jsonstr}"}'}


# ── Retry-After / status classes ──────────────────────────────────


def test_retry_after_seconds_date_and_bounds():
    now = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
    assert parse_retry_after("120") == 120.0
    assert parse_retry_after("Sat, 14 Nov 2026 12:02:30 GMT", now=now) == 150.0
    assert parse_retry_after("0") == 1.0 and parse_retry_after("999999") == 3600.0
    assert parse_retry_after("") is None and parse_retry_after("soon") is None and parse_retry_after(None) is None
    assert is_permanent_client_error(422) and is_permanent_client_error(401)
    assert not is_permanent_client_error(429) and not is_permanent_client_error(408) and not is_permanent_client_error(502)


# ── SMS http provider ─────────────────────────────────────────────


async def test_idempotency_key_reaches_the_body_and_is_per_recipient():
    mock = AsyncMock(return_value=_resp())
    with patch("app.channels.sms.safe_request", mock):
        r = await SMSChannel().send(_notif(), {**HTTP, "phone": "+1,+2"}, idempotency_key="ntf_1:sms_main")
    assert r.ok
    keys = [json.loads(c.kwargs["content"])["idempotency_key"] for c in mock.call_args_list]
    assert keys == ["ntf_1:sms_main:+1", "ntf_1:sms_main:+2"]


async def test_429_with_retry_after_is_backpressure_not_failure():
    mock = AsyncMock(return_value=_resp(429, {"detail": "rate limited"}, {"Retry-After": "240"}))
    with patch("app.channels.sms.safe_request", mock):
        r = await SMSChannel().send(_notif(), HTTP, idempotency_key="k")
    assert r.ok is False and r.retry_after == 240.0 and r.permanent is False


async def test_503_without_header_waits_a_default_minute():
    with patch("app.channels.sms.safe_request", AsyncMock(return_value=_resp(503))):
        r = await SMSChannel().send(_notif(), HTTP)
    assert r.retry_after == 60.0


async def test_success_statuses_count_as_delivered():
    dup = AsyncMock(return_value=_resp(409, {"detail": "duplicate"}))
    with patch("app.channels.sms.safe_request", dup):
        assert (await SMSChannel().send(_notif(), {**HTTP, "success_statuses": [409]})).ok is True
        r = await SMSChannel().send(_notif(), HTTP)  # without it, 409 is a final refusal
    assert r.ok is False and r.permanent is True


async def test_422_is_permanent_and_502_is_retried_normally():
    with patch("app.channels.sms.safe_request", AsyncMock(return_value=_resp(422, {"detail": "idempotency conflict"}))):
        r = await SMSChannel().send(_notif(), HTTP)
    assert r.permanent is True and r.retry_after is None
    with patch("app.channels.sms.safe_request", AsyncMock(return_value=_resp(502))):
        r = await SMSChannel().send(_notif(), HTTP)
    assert r.ok is False and r.permanent is False and r.retry_after is None


def test_success_statuses_validated_and_legacy_configs_unchanged():
    validate_config({**HTTP, "success_statuses": [409]})
    for bad in ("409", [409.5], [99], [True]):
        with pytest.raises(ValueError, match="success_statuses"):
            validate_config({**HTTP, "success_statuses": bad})
    legacy = upgrade_legacy({"gateway_url": "http://gw:5080", "phone": "+1"})
    assert "success_statuses" not in legacy  # an old config keeps the old behaviour (2xx only)


# ── Webhook ───────────────────────────────────────────────────────


async def test_webhook_body_gets_the_key_and_429_defers():
    ok = AsyncMock(return_value=_resp(200))
    with patch("app.channels._http.safe_request", ok):
        await WebhookChannel().send(_notif(), {"url": "http://hook", "body_template": '{"key": "{idempotency_key | jsonstr}"}'},
                                    idempotency_key="ntf_1:hook")
    assert json.loads(ok.call_args.kwargs["content"]) == {"key": "ntf_1:hook"}
    with patch("app.channels._http.safe_request", AsyncMock(return_value=_resp(429, headers={"Retry-After": "30"}))):
        r = await WebhookChannel().send(_notif(), {"url": "http://hook"})
    assert r.retry_after == 30.0


# ── Manager + outbox: what a delivery row does with it ────────────


@pytest.fixture
async def chan(db_session, make_channel):
    c = make_channel(kind=ChannelKind.ui, name="gw")
    db_session.add(c)
    await db_session.commit()
    return c


async def _dispatch(db_session, result):
    mgr = ChannelManager()
    with patch.object(mgr, "_get_adapter") as get:
        get.return_value = type("X", (), {"send": AsyncMock(return_value=result)})()
        out = await mgr.dispatch(_notif(), ["gw"], db_session)
    return mgr, out


async def test_retry_after_defers_without_tripping_the_breaker(db_session, chan):
    mgr = None
    for _ in range(10):  # far past the breaker threshold
        mgr, out = await _dispatch(db_session, SendResult(ok=False, error="HTTP 429", retry_after=240))
        assert "gw" in out.deferred and out.defer_sec["gw"] == 240 and "gw" not in out.failed
    assert mgr._breaker.state("gw").state == "closed"


async def test_permanent_failure_does_not_trip_the_breaker(db_session, chan):
    mgr = ChannelManager()
    with patch.object(mgr, "_get_adapter") as get:
        get.return_value = type("X", (), {"send": AsyncMock(return_value=SendResult(ok=False, error="HTTP 422", permanent=True))})()
        for _ in range(10):
            out = await mgr.dispatch(_notif(), ["gw"], db_session)
    assert out.permanent == {"gw"} and mgr._breaker.state("gw").state == "closed"


def _row(**kw) -> Delivery:
    now = datetime(2026, 11, 14, 12, 0)
    return Delivery(notification_id="ntf_1", channel="gw", purpose="primary", state=DeliveryState.pending,
                    attempts=kw.get("attempts", 0), created_at=kw.get("created_at", now))


def test_outbox_waits_exactly_retry_after_and_spends_no_attempt():
    now = datetime(2026, 11, 14, 12, 0)
    d = _row(attempts=2)
    outbox.apply_deferral(d, reason="upstream asked to retry after 240s", now=now, delay_sec=240)
    assert d.attempts == 2 and d.state == DeliveryState.pending
    assert d.next_attempt_at == now + timedelta(seconds=240)


def test_outbox_fails_a_permanent_refusal_at_once():
    d = _row(attempts=0)
    outbox.apply_attempt(d, ok=False, error="HTTP 422: idempotency conflict", permanent=True)
    assert d.state == DeliveryState.failed and d.attempts == 1 and d.next_attempt_at is None
