"""Gotify — native channel (``kind: gotify``).

``POST <server_url>/message`` with the application token in
``X-Gotify-Key`` (never in the URL, where it would end up in proxy logs).
Severity maps to Gotify's 0–10 priority (default info 2 / warning 5 /
critical 8 — Android shows ≥ 8 as a heads-up notification); the template icon
leads the title; ``admin_url`` makes a tap open the alert in Klopot
(``extras.client::notification.click``). The Gotify message id is recorded as
the delivery's ``provider_ref``. No idempotency on the Gotify side:
at-least-once.
"""
from __future__ import annotations

from typing import Any

from ..utils.redact import redact_url
from . import _http
from ._secrets import resolve_secret, scrub
from .base import BaseChannel, Notification, SendResult, admin_link

DEFAULT_PRIORITY = {"info": 2, "warning": 5, "critical": 8}


def _priority(severity: str, config: dict[str, Any]) -> int:
    mapping = config.get("priority_map") or {}
    value = mapping.get(severity) if isinstance(mapping, dict) else None
    try:
        return min(10, max(0, int(DEFAULT_PRIORITY.get(severity, 5) if value is None else value)))
    except (TypeError, ValueError):
        return DEFAULT_PRIORITY.get(severity, 5)


def build_message(notif: Notification, config: dict[str, Any]) -> dict[str, Any]:
    """JSON body for POST /message (pure, unit-tested)."""
    title = f"{notif.icon} {notif.title}" if notif.icon else notif.title
    body: dict[str, Any] = {
        "title": title[:250],
        "message": (notif.message or notif.title)[:4000],
        "priority": _priority(notif.severity, config),
        "extras": {"klopot::notification": {"id": notif.id, "type": notif.type, "severity": notif.severity}},
    }
    link = admin_link(config, notif)
    if link:
        body["extras"]["client::notification"] = {"click": {"url": link}}
    return body


class GotifyChannel(BaseChannel):
    kind = "gotify"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        server = (config.get("server_url") or "").rstrip("/")
        token = resolve_secret(config, "app_token", "app_token_ref")
        if not server:
            return SendResult(ok=False, error="gotify missing server_url")
        if not token:
            return SendResult(ok=False, error="gotify missing app_token")
        try:
            r = await _http.request(
                "gotify", "POST", f"{server}/message", json=build_message(notif, config),
                headers={"X-Gotify-Key": token, "Content-Type": "application/json"},
                timeout=float(config.get("timeout_sec") or 10), clean=lambda text: scrub(text, token),
            )
        except _http.Failed as f:
            return f.result
        if r.status_code // 100 != 2:
            return SendResult(ok=False, error=scrub(redact_url(f"gotify HTTP {r.status_code}: {r.text[:200]}"), token),
                              response={"status": r.status_code})
        response: dict[str, Any] = {"status": r.status_code}
        try:
            data = r.json()
            if isinstance(data, dict) and data.get("id") is not None:
                response["provider_ref"] = f"gotify:{data['id']}"
        except ValueError:
            pass
        return SendResult(ok=True, response=response)

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        server = (config.get("server_url") or "").rstrip("/")
        if not server:
            return {"reachable": False, "error": "no server_url configured"}
        return await _http.probe("GET", f"{server}/health")
