"""SMS channel — POST to existing ``sms-gateway`` service.

The sms-gateway (separate container, port 5080) wraps a Teltonika
RUT241 modem. We POST plaintext SMS to its ``/api/sms/send`` endpoint.

Config shape:

    {
      "gateway_url": "http://sms-gateway:5080",
      "phone": "+15555550100",
      "gateway_api_key_ref": "SMS_GATEWAY_API_KEY"  // optional
    }

Body sent to gateway::

    POST {gateway_url}/api/sms/send
    Content-Type: application/json
    {"phone": "+15555550100", "message": "title — message"}

SMS has a hard 160-char limit per segment. We truncate longer
notifications to 320 (2 segments) so the operator gets the gist.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import get_settings
from ..utils.redact import redact_url
from ..utils.safe_http import EgressBlocked, ResponseTooLarge, safe_request
from ._secrets import resolve_secret
from .base import BaseChannel, Notification, SendResult

logger = logging.getLogger(__name__)

_MAX_SMS_CHARS = 320  # 2 segments


class SMSChannel(BaseChannel):
    """Async POST to the local sms-gateway service."""

    kind = "sms"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        gateway_url = config.get("gateway_url")
        phone = config.get("phone")
        if not gateway_url:
            return SendResult(ok=False, error="Missing gateway_url")
        if not phone:
            return SendResult(ok=False, error="Missing phone")

        text = f"{notif.title}\n{notif.message}".strip()
        if len(text) > _MAX_SMS_CHARS:
            text = text[: _MAX_SMS_CHARS - 1] + "…"

        api_key = resolve_secret(config, "gateway_api_key", "gateway_api_key_ref")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key

        url = f"{gateway_url.rstrip('/')}/api/sms/send"
        body = {"phone": str(phone), "message": text}

        try:
            # SSRF-safe (audit S-05): screen the gateway URL and pin the
            # connection to an approved IP, like the webhook channel (A-04).
            r = await safe_request(
                "POST", url, json=body, headers=headers,
                timeout=15.0, block_private=get_settings().block_private_egress,
            )
            if 200 <= r.status_code < 300:
                return SendResult(ok=True, response=_safe_json(r))
            # Redact the upstream body snippet — it is stored on the delivery row
            # and readable with scope `read`, and could echo a credential (S-10).
            return SendResult(ok=False, error=redact_url(f"HTTP {r.status_code}: {r.text[:200]}"))
        except EgressBlocked as e:
            return SendResult(ok=False, error=e.reason)
        except ResponseTooLarge as e:
            return SendResult(ok=False, error=e.reason)
        except httpx.TimeoutException:
            return SendResult(ok=False, error="sms-gateway timeout")
        except httpx.HTTPError as e:
            return SendResult(ok=False, error=f"HTTP error: {type(e).__name__}: {e}")

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        gateway_url = config.get("gateway_url")
        if not gateway_url:
            return {"reachable": False, "error": "no gateway_url configured"}
        # sms-gateway exposes /api/health (200 OK) — not /health
        url = f"{gateway_url.rstrip('/')}/api/health"
        try:
            r = await safe_request(
                "GET", url, timeout=3.0,
                block_private=get_settings().block_private_egress,
            )
            return {"reachable": r.status_code == 200, "status": r.status_code}
        except EgressBlocked as e:
            return {"reachable": False, "error": e.reason}
        except Exception as e:
            return {"reachable": False, "error": str(e)[:200]}


def _safe_json(r: httpx.Response) -> dict[str, Any] | None:
    try:
        return r.json()
    except Exception:
        return None
