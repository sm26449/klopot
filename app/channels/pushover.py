"""Pushover — native channel (``kind: pushover``).

``POST https://api.pushover.net/1/messages.json`` (form-encoded). Severity
maps to priority -1 / 0 / 1 by default. **Emergency priority (2)** — repeat
every ``retry_sec`` until someone acknowledges, at most ``expire_sec`` — is an
explicit opt-in per severity (``emergency_for: ["critical"]``, default off).

An emergency send returns a *receipt*, recorded as the delivery's
``provider_ref`` (``pushover:receipt:<r>``). The provider-lifecycle service
(app/core/provider_lifecycle.py) then:

- cancels the receipt when the alert is acknowledged in Klopot
  (``POST /1/receipts/<r>/cancel.json``), as a durable, retried command;
- polls ``GET /1/receipts/<r>.json`` while it is open and, when it was
  acknowledged in the Pushover app, acknowledges the alert in Klopot — once,
  through the inbound-event inbox. Polling works behind NAT (no callback URL).

Non-emergency sends record ``pushover:<request id>``. Pushover has no
idempotency key: a retry after an ambiguous timeout may deliver twice.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import get_settings
from ..utils.redact import transport_error_text
from ..utils.safe_http import EgressBlocked, ResponseTooLarge, safe_request
from ._secrets import resolve_secret, scrub
from .base import HEALTHCHECK_TIMEOUT_SEC, BaseChannel, Notification, SendResult, admin_link

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://api.pushover.net/1"


def _api(config: dict[str, Any]) -> str:
    """The API base of a channel config (``api_url``, default Pushover's)."""
    return (str(config.get("api_url") or "").strip() or DEFAULT_API_URL).rstrip("/")


def _timeout(config: dict[str, Any]) -> float:
    return float(config.get("timeout_sec") or 10)
DEFAULT_PRIORITY = {"info": -1, "warning": 0, "critical": 1}
RECEIPT_PREFIX = "pushover:receipt:"


def _credentials(config: dict[str, Any]) -> tuple[str | None, str | None]:
    return (resolve_secret(config, "app_token", "app_token_ref"),
            resolve_secret(config, "user_key", "user_key_ref"))


def is_emergency(severity: str, config: dict[str, Any]) -> bool:
    wanted = config.get("emergency_for") or []
    return isinstance(wanted, list) and severity in wanted


def build_form(notif: Notification, config: dict[str, Any], token: str, user: str) -> dict[str, str]:
    """Form fields for messages.json (pure, unit-tested)."""
    mapping = config.get("priority_map") or {}
    raw = mapping.get(notif.severity) if isinstance(mapping, dict) else None
    try:
        priority = min(1, max(-2, int(DEFAULT_PRIORITY.get(notif.severity, 0) if raw is None else raw)))
    except (TypeError, ValueError):
        priority = DEFAULT_PRIORITY.get(notif.severity, 0)
    title = f"{notif.icon} {notif.title}" if notif.icon else notif.title
    form: dict[str, str] = {
        "token": token, "user": user,
        "title": title[:250], "message": (notif.message or notif.title)[:1024],
        "priority": str(priority),
    }
    if config.get("device"):
        form["device"] = str(config["device"])
    if is_emergency(notif.severity, config):
        form["priority"] = "2"
        form["retry"] = str(max(30, int(config.get("retry_sec") or 60)))
        form["expire"] = str(min(10800, max(int(form["retry"]), int(config.get("expire_sec") or 3600))))
    link = admin_link(config, notif)
    if link:
        form["url"] = link
        form["url_title"] = "Klopot"
    return form


class PushoverChannel(BaseChannel):
    kind = "pushover"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        token, user = _credentials(config)
        if not token or not user:
            return SendResult(ok=False, error="pushover missing app_token or user_key")
        try:
            r = await safe_request(
                "POST", f"{_api(config)}/messages.json", data=build_form(notif, config, token, user),
                timeout=_timeout(config),
                block_private=get_settings().block_private_egress,
            )
        except EgressBlocked as e:
            return SendResult(ok=False, error=e.reason)
        except ResponseTooLarge as e:
            return SendResult(ok=False, error=e.reason)
        except httpx.TimeoutException:
            return SendResult(ok=False, error="pushover timeout")
        except httpx.HTTPError as e:
            return SendResult(ok=False, error=scrub(f"pushover HTTP error: {transport_error_text(e)}", token, user)[:200])
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code // 100 != 2 or (isinstance(data, dict) and data.get("status") != 1):
            detail = data.get("errors") if isinstance(data, dict) and data.get("errors") else r.text[:200]
            return SendResult(ok=False, error=scrub(f"pushover HTTP {r.status_code}: {detail}", token, user)[:200],
                              response={"status": r.status_code})
        response: dict[str, Any] = {"status": r.status_code}
        if isinstance(data, dict) and data.get("receipt"):
            response["provider_ref"] = f"{RECEIPT_PREFIX}{data['receipt']}"
        elif isinstance(data, dict) and data.get("request"):
            response["provider_ref"] = f"pushover:{data['request']}"
        return SendResult(ok=True, response=response)

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        token, user = _credentials(config)
        if not token or not user:
            return {"reachable": False, "error": "missing app_token or user_key"}
        try:
            r = await safe_request("POST", f"{_api(config)}/users/validate.json", data={"token": token, "user": user},
                                   timeout=HEALTHCHECK_TIMEOUT_SEC, block_private=get_settings().block_private_egress)
            data = r.json() if r.status_code < 500 else {}
            return {"reachable": r.status_code < 500, "valid": bool(data.get("status") == 1)}
        except Exception as e:
            return {"reachable": False, "error": scrub(transport_error_text(e), token, user)[:200]}


# ── Receipt operations (used by app/core/provider_lifecycle.py) ─────


def receipt_of(provider_ref: str | None) -> str | None:
    if provider_ref and provider_ref.startswith(RECEIPT_PREFIX):
        return provider_ref[len(RECEIPT_PREFIX):] or None
    return None


async def cancel_receipt(config: dict[str, Any], receipt: str) -> str | None:
    """Stop an emergency's repeats. None on success, else the error."""
    token, user = _credentials(config)
    if not token:
        return "missing app_token"
    try:
        r = await safe_request("POST", f"{_api(config)}/receipts/{receipt}/cancel.json", data={"token": token},
                               timeout=_timeout(config), block_private=get_settings().block_private_egress)
    except Exception as e:
        return scrub(transport_error_text(e), token, user)[:200]
    if r.status_code // 100 == 2:
        return None
    return scrub(f"HTTP {r.status_code}: {r.text[:150]}", token, user)


async def receipt_status(config: dict[str, Any], receipt: str) -> dict[str, Any] | None:
    """The receipt's state (acknowledged, acknowledged_by_device, expired …),
    or None when it cannot be read right now."""
    token, _ = _credentials(config)
    if not token:
        return None
    try:
        r = await safe_request("GET", f"{_api(config)}/receipts/{receipt}.json", params={"token": token},
                               timeout=_timeout(config), block_private=get_settings().block_private_egress)
        if r.status_code // 100 != 2:
            # A revoked token or a gone receipt: say so, or an emergency
            # acknowledged in the app stays open here with nothing in the logs.
            logger.warning("pushover receipt %s: HTTP %s — acknowledgement unknown", receipt[:8], r.status_code)
            return None
        data = r.json()
    except Exception as e:
        # The token travels in the query string: log only the redacted text.
        logger.warning("pushover receipt %s: cannot be read (%s) — acknowledgement unknown",
                       receipt[:8], scrub(transport_error_text(e), token)[:200])
        return None
    if not (isinstance(data, dict) and data.get("status") == 1):
        logger.warning("pushover receipt %s: unexpected answer — acknowledgement unknown", receipt[:8])
        return None
    return data
