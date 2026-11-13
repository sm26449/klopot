"""BaseChannel — abstract interface for output channels.

Each channel kind subclasses this. The dispatcher calls
``send(notif, config)`` and gets back ``SendResult`` (ok flag + error
message). Adapters are simple: send or fail. Retries / circuit
breakers / rate limiting live in ``manager.py`` and are
channel-agnostic.

Plugin contract:
- ``kind`` class attribute matches the DB enum value (``"telegram"``)
- ``async def send(notif, config)`` does the I/O; raises only on
  programmer errors. Network failures, 4xx/5xx etc. → return
  ``SendResult(ok=False, error="...")``.
- ``async def healthcheck(config)`` returns ``{reachable: bool, ...}``
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


@dataclass
class SendResult:
    """Adapter return shape.

    ``error`` is set iff ``ok=False``; the manager records it in
    ``notifications_log.failed_channels[name]``.
    """

    ok: bool
    error: str | None = None
    response: dict[str, Any] | None = None  # adapter-specific debug payload


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
