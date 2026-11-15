"""SMS channel — one kind, several providers.

``provider`` picks how the text leaves Klopot:

- ``http`` (default) — any SMS gateway with an HTTP API: ``url``, ``method``,
  ``content_type`` and a ``body_template`` with ``{phone}`` and ``{text}``
  (plus every notification field, as for the webhook channel). Optional auth
  (``auth_kind`` bearer / basic / header + ``auth_header`` + ``auth_value``)
  and a ``health_url`` probed by the channel test.
- ``twilio`` — Twilio Messages API: ``account_sid``, ``auth_token``,
  ``from_number``.
- ``teltonika`` — a Teltonika RUT router's REST API (RutOS): ``router_url``,
  ``username``, ``password``, ``modem`` (default ``1-1``). Logs in on every
  send (``POST /api/login``), then ``POST /api/messages/actions/send``.

``phone`` is one E.164 number or several separated by commas; the delivery
succeeds only when every recipient was accepted. Text is ``title`` + newline
+ ``message``, cut to ``max_chars`` (default 320 = two segments).

Every request goes through ``safe_request`` (SSRF screening, IP pinning).
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from ..config import get_settings
from ..core import rendering
from ..utils.http_retry import BACKPRESSURE_STATUSES, is_permanent_client_error, parse_retry_after
from ..utils.redact import redact_url, transport_error_text
from ..utils.safe_http import EgressBlocked, ResponseTooLarge, safe_request
from ._secrets import resolve_secret
from .base import BaseChannel, Notification, SendResult
from .sms_config import LEGACY_BODY as DEFAULT_BODY
from .sms_config import PROVIDERS, success_statuses
from .webhook import _build_template_ctx

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CHARS = 320  # 2 segments
_TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class _SendError(Exception):
    """A provider refused the message; the text goes to the delivery row.

    ``retry_after``: the provider asked to come back later (429 / 503) —
    seconds. ``permanent``: a retry cannot succeed (a 4xx such as 422).
    """

    def __init__(self, message: str, *, retry_after: float | None = None, permanent: bool = False):
        super().__init__(message)
        self.retry_after = retry_after
        self.permanent = permanent


def recipients(config: dict[str, Any]) -> list[str]:
    raw = config.get("phone") or ""
    items = raw if isinstance(raw, list) else str(raw).split(",")
    return [p.strip() for p in items if str(p).strip()]


def sms_text(notif: Notification, config: dict[str, Any]) -> str:
    try:
        limit = max(1, int(config.get("max_chars") or _DEFAULT_MAX_CHARS))
    except (TypeError, ValueError):
        limit = _DEFAULT_MAX_CHARS
    text = f"{notif.title}\n{notif.message}".strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _auth_headers(config: dict[str, Any]) -> dict[str, str]:
    kind = config.get("auth_kind") or ""
    if not kind:
        return {}
    value = resolve_secret(config, "auth_value", "auth_value_ref")
    if not value:
        raise _SendError("auth_kind set but no auth_value resolved")
    if kind == "bearer":
        return {"Authorization": f"Bearer {value}"}
    if kind == "basic":
        return {"Authorization": f"Basic {value}"}
    if kind == "header":
        return {(config.get("auth_header") or "Authorization").strip(): value}
    raise _SendError(f"unknown auth_kind: {kind}")


def _check(r: httpx.Response, success_statuses: frozenset[int] = frozenset()) -> dict[str, Any] | None:
    """The response body of an accepted request, or _SendError saying how to
    treat the refusal: 429 / 503 → wait (Retry-After, default 60 s); other 4xx
    except 408 → permanent; anything else → retry with backoff."""
    if 200 <= r.status_code < 300 or r.status_code in success_statuses:
        try:
            body = r.json()
            out = body if isinstance(body, dict) else {"body": body}
        except Exception:
            out = {}
        return {**out, "status": r.status_code} if r.status_code >= 300 else (out or None)
    # The upstream body is stored on the delivery row (scope `read`) and could
    # echo a credential — redact it (audit S-10).
    message = redact_url(f"HTTP {r.status_code}: {r.text[:200]}")
    if r.status_code in BACKPRESSURE_STATUSES:
        raise _SendError(message, retry_after=parse_retry_after(r.headers.get("Retry-After")) or 60.0)
    raise _SendError(message, permanent=is_permanent_client_error(r.status_code))


class SMSChannel(BaseChannel):
    kind = "sms"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        provider = config.get("provider") or "http"
        if provider not in PROVIDERS:
            return SendResult(ok=False, error=f"unknown SMS provider: {provider}")
        phones = recipients(config)
        if not phones:
            return SendResult(ok=False, error="Missing phone")
        text = sms_text(notif, config)
        block = get_settings().block_private_egress
        responses: list[Any] = []
        try:
            token = await _teltonika_login(config, block) if provider == "teltonika" else None
            for phone in phones:
                if provider == "http":
                    responses.append(await _send_http(notif, config, phone, text, block, idempotency_key))
                elif provider == "twilio":
                    responses.append(await _send_twilio(config, phone, text, block))
                else:
                    responses.append(await _send_teltonika(config, token or "", phone, text, block))
        except _SendError as e:
            # With several recipients, the ones before the refusal were sent; a
            # retry sends them again unless the gateway deduplicates on
            # idempotency_key (put "{idempotency_key}:{phone}" in the body).
            return SendResult(ok=False, error=str(e), response={"sent": len(responses)},
                              retry_after=e.retry_after, permanent=e.permanent)
        except (EgressBlocked, ResponseTooLarge) as e:
            return SendResult(ok=False, error=e.reason)
        except httpx.TimeoutException:
            return SendResult(ok=False, error=f"SMS {provider} timeout")
        except httpx.HTTPError as e:
            return SendResult(ok=False, error=f"HTTP error: {transport_error_text(e)}")
        return SendResult(ok=True, response={"provider": provider, "sent": len(phones),
                                             "responses": responses[:5]})

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        provider = config.get("provider") or "http"
        url = {
            "http": config.get("health_url"),
            "twilio": "https://api.twilio.com/",
            "teltonika": (config.get("router_url") or "").rstrip("/") + "/api/login" if config.get("router_url") else None,
        }.get(provider)
        if not url:
            return {"reachable": None, "note": "no health_url configured"}
        try:
            r = await safe_request("GET", url, timeout=3.0, block_private=get_settings().block_private_egress)
            # Reachability, not authorization: any HTTP answer below 500 means
            # the service is there (a login endpoint answers 405 to a GET).
            return {"reachable": r.status_code < 500, "status": r.status_code}
        except EgressBlocked as e:
            return {"reachable": False, "error": e.reason}
        except Exception as e:
            return {"reachable": False, "error": str(e)[:200]}


async def _send_http(notif: Notification, config: dict[str, Any], phone: str, text: str, block: bool,
                     idempotency_key: str | None = None) -> Any:
    url = config.get("url")
    if not url:
        raise _SendError("Missing url")
    content_type = config.get("content_type") or "application/json"
    # idempotency_key: identical on the first attempt and every retry of this
    # delivery — a gateway that deduplicates on it never sends twice.
    ctx = {**_build_template_ctx(notif), "phone": phone, "text": text, "idempotency_key": idempotency_key or notif.id}
    try:
        body = rendering.render(config.get("body_template") or DEFAULT_BODY, ctx)
    except Exception as e:
        raise _SendError(f"body template error: {e}") from None
    if content_type == "application/json":
        try:
            json.loads(body)
        except json.JSONDecodeError as e:
            raise _SendError(f"rendered body is not valid JSON: {e}") from None
    headers = {"Content-Type": content_type, **_auth_headers(config)}
    r = await safe_request((config.get("method") or "POST").upper(), url, content=body, headers=headers,
                           timeout=15.0, block_private=block)
    return _check(r, success_statuses(config))


async def _send_twilio(config: dict[str, Any], phone: str, text: str, block: bool) -> Any:
    sid = (config.get("account_sid") or "").strip()
    sender = (config.get("from_number") or "").strip()
    token = resolve_secret(config, "auth_token", "auth_token_ref")
    if not (sid and sender and token):
        raise _SendError("Twilio needs account_sid, auth_token and from_number")
    basic = base64.b64encode(f"{sid}:{token}".encode()).decode()
    r = await safe_request(
        "POST", _TWILIO_URL.format(sid=sid), data={"To": phone, "From": sender, "Body": text},
        headers={"Authorization": f"Basic {basic}"}, timeout=15.0, block_private=block,
    )
    body = _check(r) or {}
    return {"sid": body.get("sid"), "status": body.get("status")}


async def _teltonika_login(config: dict[str, Any], block: bool) -> str:
    base = (config.get("router_url") or "").rstrip("/")
    user = config.get("username") or ""
    password = resolve_secret(config, "password", "password_ref")
    if not (base and user and password):
        raise _SendError("Teltonika needs router_url, username and password")
    r = await safe_request("POST", f"{base}/api/login", json={"username": user, "password": password},
                           timeout=10.0, block_private=block)
    body = _check(r) or {}
    data = body.get("data")
    token = (data.get("token") if isinstance(data, dict) else None) or body.get("token")
    if not token:
        raise _SendError("Teltonika login returned no token")
    return str(token)


async def _send_teltonika(config: dict[str, Any], token: str, phone: str, text: str, block: bool) -> Any:
    base = (config.get("router_url") or "").rstrip("/")
    r = await safe_request(
        "POST", f"{base}/api/messages/actions/send",
        json={"data": {"number": phone, "message": text, "modem": config.get("modem") or "1-1"}},
        headers={"Authorization": f"Bearer {token}"}, timeout=15.0, block_private=block,
    )
    return _check(r)
