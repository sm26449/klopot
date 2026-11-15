"""Webhook input — receives POST values from external systems.

Different from MQTT: there's no persistent connection, no
subscribe loop. The HTTP endpoint at
``POST /v1/inputs/{id}/webhook`` receives bodies, validates auth,
and delivers them to the resolver via the manager's on_value
callback.

Adapter responsibilities:
- Hold per-input config (auth_token_ref, allowed_ips)
- Verify auth on each delivery (called from the API endpoint)
- Track health (last_msg_ts, count, errors)
- Update on config changes (no socket to recycle, just config swap)

Topic scheme: a single virtual topic per webhook input,
``webhook:<input_name>``. Variables map to it the same way they
map to MQTT topics. JSONPath into the payload still works.
"""
from __future__ import annotations

import hmac
import logging
import time
from typing import Any

from ._secrets_helper import resolve_secret_local
from .base import BaseInput, ValueCallback

logger = logging.getLogger(__name__)


class WebhookInput(BaseInput):
    """Push-based input. The endpoint dispatches to ``deliver()``."""

    kind = "webhook"

    def __init__(self, *, name: str, config: dict[str, Any], on_value: ValueCallback) -> None:
        super().__init__(name=name, config=config, on_value=on_value)
        self._last_msg_ts: float | None = None
        self._msg_count: int = 0
        self._last_error: str | None = None
        # Secure default: if a token is configured but auth_required is not
        # explicitly set, enforce auth — a configured token must not give
        # false assurance while unauthenticated posts are accepted (audit
        # F35). An explicit auth_required=False is a deliberate opt-out.
        self._auth_required = auth_required(config)

    @property
    def topic(self) -> str:
        """Virtual topic clients use to map variables to this input."""
        return f"webhook:{self.name}"

    # ── BaseInput surface ───────────────────────────────────────

    async def start(self) -> None:
        # Push input — no connection. Just record we're ready.
        logger.info("webhook input %s ready (auth_required=%s)", self.name, self._auth_required)

    async def stop(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {
            "connected": True,
            "last_msg_ts": self._last_msg_ts,
            "msg_count": self._msg_count,
            "error": self._last_error,
            "topic": self.topic,
        }

    async def update_topics(self, topics: dict[str, Any]) -> None:
        # Webhook doesn't filter — variables map to its single virtual topic
        return None

    # ── Auth + delivery ─────────────────────────────────────────

    def check_auth(self, header_token: str | None) -> bool:
        """Verify caller-supplied token against config. Returns True
        if accepted (or if auth_required is False)."""
        return webhook_auth_ok(self.config, header_token)

    async def deliver(self, payload: Any) -> None:
        """Called by the API endpoint after auth passes."""
        self._last_msg_ts = time.time()
        self._msg_count += 1
        try:
            await self.on_value(self.topic, payload, "webhook")
        except Exception as e:
            self._last_error = f"{type(e).__name__}: {e}"[:200]
            raise


def auth_required(config: dict[str, Any]) -> bool:
    """Whether a webhook input demands a token.

    Secure default: if a token is configured but ``auth_required`` is not
    explicitly set, enforce auth — a configured token must not give false
    assurance while unauthenticated posts are accepted (audit F35). An
    explicit ``auth_required=False`` is a deliberate opt-out."""
    if "auth_required" in config:
        return bool(config.get("auth_required"))
    return bool(config.get("auth_token") or config.get("auth_token_ref"))


def webhook_auth_ok(config: dict[str, Any], header_token: str | None) -> bool:
    """Whether ``header_token`` opens the webhook input configured by
    ``config``. Pure, so the endpoint can check it before anything about the
    input (its adapter's state) is revealed (review K10)."""
    if not auth_required(config):
        return True
    configured = resolve_secret_local(config, "auth_token", "auth_token_ref")
    if not configured:
        # Required but not configured = always reject
        return False
    return header_token is not None and _constant_time_eq(header_token, configured)


def _constant_time_eq(a: str, b: str) -> bool:
    """Constant-time token comparison via the stdlib primitive (audit S-13).

    ``hmac.compare_digest`` is the vetted constant-time compare; it replaces a
    hand-rolled loop whose explicit length early-return leaked the token length
    through timing."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
