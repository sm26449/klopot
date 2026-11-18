"""Output-channel adapter contract.

- ``kind`` class attribute matches the DB enum value (``"telegram"``).
- ``async def send(notif, config, *, idempotency_key=None) -> SendResult``:
  ``notif`` is the rendered content, ``config`` the channel's effective config
  for this delivery; ``idempotency_key`` stays the same across attempts of one
  delivery — forward it to a provider that de-duplicates. Return a failed
  ``SendResult`` for expected transport / provider failures (``retry_after``
  asks for a later attempt, ``permanent`` refuses for good); raise only on
  programmer errors.
- ``async def healthcheck(config)`` optionally probes reachability; ``close()``
  releases resources.

The channel manager (``manager.py``) enforces send timeouts, rate limits and
circuit breakers; the durable outbox (``app/core/outbox.py``) and the delivery
worker own the retries.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Notification:
    """Carrier shape passed to channel adapters.

    Built by the dispatcher from the rendered template + envelope.
    Adapters get exactly the fields they need — no DB row, no
    template/rule references."""

    id: str
    type: str
    severity: str
    icon: str | None
    title: str
    message: str
    fired_at: datetime
    vars_payload: dict[str, Any] | None = None
    rule_id: int | None = None
    incident_id: str | None = None


@dataclass
class SendResult:
    """Adapter return shape.

    ``error`` is set iff ``ok=False``; the manager records it in
    ``notifications_log.failed_channels[name]``.
    """

    ok: bool
    error: str | None = None
    response: dict[str, Any] | None = None  # adapter-specific debug payload
    # The upstream asked to come back later (429 / 503 with Retry-After):
    # seconds to wait. The delivery is DEFERRED by that much — no attempt
    # spent, breaker untouched — instead of the exponential backoff.
    retry_after: float | None = None
    # The upstream refused this message for good (e.g. a 4xx such as 422):
    # fail it now instead of retrying, without tripping the breaker.
    permanent: bool = False


class BaseChannel(ABC):
    """Abstract output channel."""

    kind: str = "base"

    @abstractmethod
    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        """Deliver one notification. Must be async + non-blocking.

        ``idempotency_key`` is a stable per-delivery identity (same on the
        first attempt and every retry — audit F23). Adapters whose
        destination supports deduplication (e.g. webhook) should forward it;
        others may ignore it.
        """

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        """Optional reachability probe. Default: assume ok."""
        return {"reachable": True}

    async def close(self) -> None:
        """Release persistent resources on service shutdown."""
        return None


# Type of the notification POST /v1/channels/{id}/test sends.
CHANNEL_TEST_TYPE = "channel_test"

# Every adapter's reachability probe (the channel test's "health" step).
HEALTHCHECK_TIMEOUT_SEC = 5.0


def admin_link(config: dict[str, object], notif: Notification) -> str | None:
    """Where tapping a notification opens Klopot (channels with ``admin_url``).

    A real alert opens its log entry; a channel test has no log entry, so it
    opens the Channels page instead.
    """
    admin = str(config.get("admin_url") or "").rstrip("/")
    if not admin:
        return None
    if notif.type == CHANNEL_TEST_TYPE:
        return f"{admin}/admin/#/channels"
    return f"{admin}/admin/#/log?id={notif.id}"
