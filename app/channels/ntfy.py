"""ntfy — native channel (``kind: ntfy``).

Publishes with ntfy's JSON API (``POST <server_url>`` with ``{"topic", …}``)
rather than headers, so titles keep UTF-8 (diacritics, the template's
emoji icon). The ``webhook`` channel's ntfy preset keeps working; this kind
adds what the preset loses: severity → priority, tags, a click link and a
"View" button back to the admin UI, and the ntfy message id recorded as the
delivery's ``provider_ref``.

Config:

- ``server_url`` (default ``https://ntfy.sh``), ``topic`` / ``topic_ref``
  (required; write-only — on ntfy the topic name is the credential)
- ``token`` / ``token_ref``: access token, sent as ``Authorization: Bearer``
- ``priority_map``: ``{"info": 2, "warning": 3, "critical": 5}`` (default)
- ``tags``: extra ntfy tags (list of strings)
- ``admin_url``: e.g. ``https://alerts.example.com`` → click link and
  "View" button to ``<admin_url>/admin/#/log?id=<notification id>``

ntfy has no idempotency support: a retried send can publish twice
(at-least-once), like SMS.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import get_settings
from ..utils.redact import redact_url, transport_error_text
from ..utils.safe_http import EgressBlocked, ResponseTooLarge, safe_request
from ._secrets import resolve_secret, scrub
from .base import HEALTHCHECK_TIMEOUT_SEC, BaseChannel, Notification, SendResult, admin_link

logger = logging.getLogger(__name__)

DEFAULT_SERVER = "https://ntfy.sh"
DEFAULT_PRIORITY = {"info": 2, "warning": 3, "critical": 5}


def _priority(severity: str, config: dict[str, Any]) -> int:
    mapping = config.get("priority_map") or {}
    value = mapping.get(severity) if isinstance(mapping, dict) else None
    if value is None:
        value = DEFAULT_PRIORITY.get(severity, 3)
    try:
        return min(5, max(1, int(value)))
    except (TypeError, ValueError):
        return 3


def build_message(notif: Notification, config: dict[str, Any]) -> dict[str, Any]:
    """The JSON body published to ntfy (pure, unit-tested)."""
    title = f"{notif.icon} {notif.title}" if notif.icon else notif.title
    body: dict[str, Any] = {
        "topic": config["topic"],
        "title": title[:250],
        "message": (notif.message or notif.title)[:4000],
        "priority": _priority(notif.severity, config),
        "tags": [notif.severity, *[str(t) for t in (config.get("tags") or []) if str(t)]][:10],
    }
    link = admin_link(config, notif)
    if link:
        body["click"] = link
        body["actions"] = [{"action": "view", "label": "Klopot", "url": link, "clear": False}]
    return body


class NtfyChannel(BaseChannel):
    kind = "ntfy"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        topic = resolve_secret(config, "topic", "topic_ref")
        if not topic:
            return SendResult(ok=False, error="ntfy missing topic")
        server = (config.get("server_url") or DEFAULT_SERVER).rstrip("/")
        headers = {"Content-Type": "application/json"}
        token = resolve_secret(config, "token", "token_ref")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            r = await safe_request(
                "POST", server, json=build_message(notif, {**config, "topic": topic}), headers=headers,
                timeout=float(config.get("timeout_sec") or 10),
                block_private=get_settings().block_private_egress,
            )
        except EgressBlocked as e:
            return SendResult(ok=False, error=e.reason)
        except ResponseTooLarge as e:
            return SendResult(ok=False, error=e.reason)
        except httpx.TimeoutException:
            return SendResult(ok=False, error="ntfy timeout")
        except httpx.HTTPError as e:
            return SendResult(ok=False, error=scrub(f"ntfy HTTP error: {transport_error_text(e)}", token)[:200])
        if r.status_code // 100 != 2:
            return SendResult(ok=False, error=scrub(redact_url(f"ntfy HTTP {r.status_code}: {r.text[:200]}"), token),
                              response={"status": r.status_code})
        message_id = None
        try:
            data = r.json()
            message_id = data.get("id") if isinstance(data, dict) else None
        except ValueError:
            pass
        response: dict[str, Any] = {"status": r.status_code}
        if isinstance(message_id, str) and message_id:
            response["provider_ref"] = f"ntfy:{message_id}"
        return SendResult(ok=True, response=response)

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        server = (config.get("server_url") or DEFAULT_SERVER).rstrip("/")
        try:
            r = await safe_request(
                "GET", f"{server}/v1/health", timeout=HEALTHCHECK_TIMEOUT_SEC,
                block_private=get_settings().block_private_egress,
            )
            healthy = r.status_code == 200 and bool((r.json() or {}).get("healthy"))
            return {"reachable": r.status_code < 500, "healthy": healthy, "status": r.status_code}
        except EgressBlocked as e:
            return {"reachable": False, "error": e.reason}
        except Exception as e:
            return {"reachable": False, "error": transport_error_text(e)[:200]}
