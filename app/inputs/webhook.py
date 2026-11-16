"""Webhook input — receives POST values from external systems.

Different from MQTT: there's no persistent connection, no
subscribe loop. The HTTP endpoint at
``POST /v1/inputs/{id}/webhook`` receives bodies, validates auth,
and delivers them to the resolver via the manager's on_value
callback.

Adapter responsibilities:
- Hold per-input config (auth_token / auth_token_ref, auth_required)
- Verify auth on each delivery (called from the API endpoint)
- Track health (last_msg_ts, count, errors)
- Update on config changes (no socket to recycle, just config swap)

Topic scheme: a single virtual topic per webhook input,
``webhook:<input_name>``. Variables map to it the same way they
map to MQTT topics. JSONPath into the payload still works.

Inbound authentication (shared by every kind posting to that endpoint —
webhook, sms_inbox, alertmanager) is defined here once: a token is required
unless the configuration says ``auth_required: false``, and a configuration
that requires a token without having one is refused when it is saved
(``validate_inbound_auth``), not discovered later as an input that rejects —
or, before 1.2, accepted — everything. A token is also judged by its length
(``MIN_TOKEN_LENGTH``) whenever the authentication is set or changed; an
input saved before the floor keeps working, and is flagged (``short_token``).
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


# Kinds that receive posts at POST /v1/inputs/{id}/webhook.
INBOUND_KINDS = frozenset({"webhook", "sms_inbox", "alertmanager"})
# The fields that decide how an inbound input authenticates.
AUTH_FIELDS = ("auth_required", "auth_token", "auth_token_ref")
# Characters an inbound token needs: ~190 bits as base64, beyond guessing
# even before the per-address budget (public-exposure review F3).
MIN_TOKEN_LENGTH = 32


def auth_required(config: dict[str, Any]) -> bool:
    """Whether an inbound input demands a token: always, unless its config
    says ``auth_required: false`` — the literal boolean (anything else,
    including the string "false", fails closed). Until 1.2 a missing flag
    meant "only if a token is set", which left an input without a token open
    to anyone (public-exposure review)."""
    return config.get("auth_required", True) is not False


def short_token(config: dict[str, Any]) -> str | None:
    """Why the token an inbound input checks is too short, or ``None``. Only
    a token that can be read now is judged: an ``auth_token_ref`` whose
    variable is not set yet cannot be (the input refuses every post until it
    is)."""
    if not auth_required(config):
        return None
    token = resolve_secret_local(config, "auth_token", "auth_token_ref")
    if token is None or len(token) >= MIN_TOKEN_LENGTH:
        return None
    where = f"the variable {config['auth_token_ref']}" if config.get("auth_token_ref") else "auth_token"
    return (f"{where} has {len(token)} characters; an input token needs at least {MIN_TOKEN_LENGTH} "
            "(e.g. openssl rand -base64 32)")


def auth_changed(before: dict[str, Any] | None, after: dict[str, Any]) -> bool:
    """Whether ``after`` authenticates differently from ``before`` (``None``
    = a new input): the cue to judge the token again."""
    return before is None or any(before.get(f) != after.get(f) for f in AUTH_FIELDS)


def validate_inbound_auth(config: dict[str, Any], *, judge_token: bool = True) -> None:
    """Refuse an inbound input's config that cannot authenticate as intended:
    ``auth_required`` that is not a boolean, auth required (the default) with
    no ``auth_token`` / ``auth_token_ref`` — and, with ``judge_token``, a
    token shorter than ``MIN_TOKEN_LENGTH``. Raises ``ValueError`` with the
    fix in the message.

    Callers judge the token when the authentication is set or changed
    (``auth_changed``), so an input saved before the floor can still be
    edited, disabled or exported — it is flagged instead (``short_token``)."""
    flag = config.get("auth_required", True)
    if not isinstance(flag, bool):
        raise ValueError("auth_required must be true or false")
    if flag and not (config.get("auth_token") or config.get("auth_token_ref")):
        raise ValueError(
            "this input needs a token: set auth_token (or auth_token_ref) — or set "
            "auth_required to false to accept posts without one"
        )
    problem = short_token(config) if judge_token else None
    if problem:
        raise ValueError(problem)


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
