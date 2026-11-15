"""WebhookChannel tests with a mocked httpx.AsyncClient."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.channels.base import Notification
from app.channels.webhook import WebhookChannel, _build_template_ctx


def _notif(**overrides):
    defaults = dict(
        id="ntf_test",
        type="t",
        severity="warning",
        icon="⚠️",
        title="Battery Low",
        message="SOC 18%",
        fired_at=datetime(2026, 5, 10, 12, 0, 0),
        vars_payload={"soc": 18, "temp": 22.5},
        rule_id=42,
    )
    defaults.update(overrides)
    return Notification(**defaults)


def _patch_request(*, status: int = 200, text: str = "ok"):
    """Patch the SSRF-safe send seam (A-04). The webhook now delegates the
    actual request to ``safe_request`` (which screens + pins the connection,
    tested separately), so tests assert on what the webhook passes to it. The
    returned holder exposes ``.request`` = the mock so existing call-arg
    assertions still read ``client.request.call_args``."""
    response = MagicMock()
    response.status_code = status
    response.text = text
    safe_req = AsyncMock(return_value=response)
    holder = MagicMock()
    holder.request = safe_req
    return patch("app.channels.webhook.safe_request", safe_req), holder


# ── Config validation ─────────────────────────────────────────────


async def test_missing_url():
    r = await WebhookChannel().send(_notif(), {})
    assert r.ok is False and "url" in r.error


# ── Successful sends ──────────────────────────────────────────────


async def test_default_body_template_and_post():
    patcher, client = _patch_request(status=200)
    with patcher:
        r = await WebhookChannel().send(_notif(), {"url": "https://hook"})
    assert r.ok is True
    method, url = client.request.call_args.args[:2]
    assert method == "POST"
    assert url == "https://hook"
    body = client.request.call_args.kwargs["content"]
    assert "Battery Low" in body
    assert "warning" in body


async def test_custom_method_put():
    patcher, client = _patch_request(status=200)
    with patcher:
        await WebhookChannel().send(
            _notif(),
            {"url": "https://hook", "method": "PUT"},
        )
    assert client.request.call_args.args[0] == "PUT"


async def test_custom_body_template_with_vars_payload():
    """Body template can reference flat vars_payload entries."""
    patcher, client = _patch_request(status=200)
    template = '{"text": "soc={soc} temp={temp}"}'
    with patcher:
        await WebhookChannel().send(
            _notif(),
            {"url": "https://hook", "body_template": template},
        )
    body = client.request.call_args.kwargs["content"]
    assert "soc=18" in body and "temp=22.5" in body


async def test_bearer_auth_attached():
    patcher, client = _patch_request(status=200)
    with patcher:
        await WebhookChannel().send(
            _notif(),
            {
                "url": "https://hook",
                "auth_kind": "bearer",
                "auth_value": "TOKEN_VALUE",
            },
        )
    headers = client.request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer TOKEN_VALUE"


async def test_header_auth_with_name_value():
    patcher, client = _patch_request(status=200)
    with patcher:
        await WebhookChannel().send(
            _notif(),
            {
                "url": "https://hook",
                "auth_kind": "header",
                "auth_value": "X-Webhook-Token: abc123",
            },
        )
    headers = client.request.call_args.kwargs["headers"]
    assert headers.get("X-Webhook-Token") == "abc123"


async def test_unknown_auth_kind_returns_error():
    r = await WebhookChannel().send(
        _notif(),
        {"url": "https://hook", "auth_kind": "magic", "auth_value": "x"},
    )
    assert r.ok is False and "auth_kind" in r.error


async def test_auth_kind_without_value_returns_error():
    r = await WebhookChannel().send(
        _notif(),
        {"url": "https://hook", "auth_kind": "bearer"},
    )
    assert r.ok is False
    assert "no value resolved" in r.error


# ── JSON validation ───────────────────────────────────────────────


async def test_json_body_is_validated():
    """Default content-type is application/json — body must be valid
    JSON. Invalid JSON returns an error WITHOUT firing the request."""
    patcher, client = _patch_request(status=200)
    bad_template = "{this is not valid json"
    with patcher:
        r = await WebhookChannel().send(
            _notif(),
            {"url": "https://hook", "body_template": bad_template},
        )
    assert r.ok is False
    assert "valid JSON" in r.error
    client.request.assert_not_called()


async def test_form_content_type_skips_json_validation():
    patcher, client = _patch_request(status=200)
    with patcher:
        r = await WebhookChannel().send(
            _notif(),
            {
                "url": "https://hook",
                "content_type": "application/x-www-form-urlencoded",
                "body_template": "x=1&y=2",
            },
        )
    assert r.ok is True


# ── Status code handling ──────────────────────────────────────────


async def test_201_treated_as_success_by_default():
    patcher, _ = _patch_request(status=201)
    with patcher:
        r = await WebhookChannel().send(_notif(), {"url": "https://hook"})
    assert r.ok is True


async def test_4xx_returns_error():
    patcher, _ = _patch_request(status=403, text="forbidden")
    with patcher:
        r = await WebhookChannel().send(_notif(), {"url": "https://hook"})
    assert r.ok is False and "403" in r.error


async def test_explicit_expected_status_int():
    """Caller can pin the success code (e.g. Slack returns 200, but
    a custom service returns 207)."""
    patcher, _ = _patch_request(status=207)
    with patcher:
        r = await WebhookChannel().send(
            _notif(),
            {"url": "https://hook", "expected_status": 207},
        )
    assert r.ok is True


async def test_explicit_expected_status_list():
    patcher, _ = _patch_request(status=204)
    with patcher:
        r = await WebhookChannel().send(
            _notif(),
            {"url": "https://hook", "expected_status": [200, 204]},
        )
    assert r.ok is True


# ── Failure paths ─────────────────────────────────────────────────


async def test_timeout_returns_error():
    with patch(
        "app.channels.webhook.safe_request",
        AsyncMock(side_effect=httpx.TimeoutException("late")),
    ):
        r = await WebhookChannel().send(_notif(), {"url": "https://hook"})
    assert r.ok is False and "timeout" in r.error.lower()


# ── A18: JSON is built/escaped, not text-interpolated ─────────────


async def test_default_body_valid_json_with_quotes_and_newline():
    """A title containing a quote and newline used to produce invalid
    JSON (text interpolation) and block delivery. The default body is now
    json.dumps of a dict — always valid, and the request IS sent."""
    import json

    patcher, client = _patch_request(status=200)
    nasty = 'Grid "down"\nnow'
    with patcher:
        r = await WebhookChannel().send(
            _notif(title=nasty, message='SOC "18%"'),
            {"url": "https://hook"},
        )
    assert r.ok is True
    client.request.assert_called_once()
    body = client.request.call_args.kwargs["content"]
    parsed = json.loads(body)  # must be valid JSON
    assert parsed["title"] == nasty
    assert parsed["message"] == 'SOC "18%"'


async def test_default_body_build_is_valid_json_unit():
    import json

    from app.channels.webhook import _build_default_body

    ctx = _build_template_ctx(_notif(title='a"b', message="c\nd"))
    parsed = json.loads(_build_default_body(ctx))
    assert parsed["title"] == 'a"b'
    assert parsed["message"] == "c\nd"


async def test_json_webhook_presets_survive_nasty_title():
    """Every JSON preset body_template must render to valid JSON even when
    the title/message carry quotes and newlines (audit A18)."""
    import json

    from app.meta_kinds import describe_kinds

    presets = describe_kinds()["webhook_presets"]
    nasty = _notif(title='He said "boom"\nline2', message='msg "x"\ny')
    for p in presets:
        cfg = p["config"]
        if cfg.get("content_type") != "application/json":
            continue  # ntfy is text/plain
        patcher, client = _patch_request(status=cfg.get("expected_status", 200))
        # Some presets (home_assistant) set auth_kind; supply a value so the
        # send reaches the body step — this test is about JSON validity.
        full = {"url": "https://hook", "auth_value": "TESTTOKEN", **cfg}
        with patcher:
            r = await WebhookChannel().send(nasty, full)
        assert r.ok is True, f"preset {p['id']} failed: {r.error}"
        body = client.request.call_args.kwargs["content"]
        json.loads(body)  # valid JSON for every preset


# ── Template context builder ──────────────────────────────────────


def test_build_template_ctx_exposes_all_fields():
    ctx = _build_template_ctx(_notif())
    assert ctx["title"] == "Battery Low"
    assert ctx["severity"] == "warning"
    assert ctx["severity_emoji"] == "⚠️"
    assert ctx["rule_id"] == 42
    assert ctx["soc"] == 18  # from vars_payload
    assert ctx["temp"] == 22.5


def test_build_template_ctx_no_payload():
    ctx = _build_template_ctx(_notif(vars_payload=None))
    # Doesn't crash; vars_payload keys absent
    assert "soc" not in ctx


def test_build_template_ctx_payload_does_not_overwrite_core():
    """A var in vars_payload named 'severity' must NOT shadow the
    real notif.severity — we use setdefault to preserve the core
    fields."""
    ctx = _build_template_ctx(_notif(vars_payload={"severity": "ATTACKER"}))
    assert ctx["severity"] == "warning"


# ── F23: stable idempotency key + id in the default body ──────────

async def test_idempotency_key_header_is_set_and_stable():
    patcher, client = _patch_request(status=200)
    with patcher:
        await WebhookChannel().send(
            _notif(), {"url": "https://hook"}, idempotency_key="ntf_x:webhook_a",
        )
    headers = client.request.call_args.kwargs["headers"]
    assert headers["Idempotency-Key"] == "ntf_x:webhook_a"


async def test_idempotency_key_defaults_to_notif_id():
    patcher, client = _patch_request(status=200)
    with patcher:
        await WebhookChannel().send(_notif(id="ntf_abc"), {"url": "https://hook"})
    headers = client.request.call_args.kwargs["headers"]
    assert headers["Idempotency-Key"] == "ntf_abc"


async def test_caller_supplied_idempotency_header_is_not_overridden():
    patcher, client = _patch_request(status=200)
    with patcher:
        await WebhookChannel().send(
            _notif(), {"url": "https://hook", "headers": {"Idempotency-Key": "mine"}},
            idempotency_key="ntf_x:webhook_a",
        )
    headers = client.request.call_args.kwargs["headers"]
    assert headers["Idempotency-Key"] == "mine"


async def test_default_body_contains_notification_id():
    import json as _json
    patcher, client = _patch_request(status=200)
    with patcher:
        await WebhookChannel().send(_notif(id="ntf_bodyid"), {"url": "https://hook"})
    body = _json.loads(client.request.call_args.kwargs["content"])
    assert body["id"] == "ntf_bodyid"
    assert body["type"] == "t"
