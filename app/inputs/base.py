"""Input adapter contract.

Registered adapters (``app/inputs/__init__.py``): mqtt, http_poll, webhook,
sms_inbox and alertmanager. The ``schedule`` and ``email_imap`` enum values
have no adapter: schedule values are produced by the input manager itself.

- Construct with keyword arguments ``name``, ``config`` and ``on_value``; the
  async ``on_value(topic, payload, source_kind)`` callback receives raw
  input, which the resolver (``app.core.variable_resolver``) maps into named
  variables.
- ``await start()`` begins work and returns promptly; ``await stop()`` cancels
  and awaits owned tasks and closes resources.
- ``health()`` returns a snapshot for ``/v1/health`` and
  ``/v1/inputs/{id}/health``.
- ``await update_topics(topics)`` is an optional hot-reload hook (MQTT).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

# Callback signature used by adapters to deliver raw payloads.
# topic = MQTT topic / HTTP URL / "schedule:<name>" / etc.
# payload = raw bytes / parsed JSON / scalar — adapter-defined.
# source_kind = adapter's `kind` for source_topic tagging.
ValueCallback = Callable[[str, Any, str], Awaitable[None]]


class BaseInput(ABC):
    """Abstract input adapter."""

    kind: str = "base"

    def __init__(self, *, name: str, config: dict[str, Any], on_value: ValueCallback) -> None:
        self.name = name
        self.config = config
        self.on_value = on_value

    @classmethod
    def validate_config(cls, config: dict[str, Any], *, before: dict[str, Any] | None = None) -> None:
        """Refuse a config this kind cannot run as intended: raise
        ``ValueError`` with the fix in the message. Called when an input is
        saved (REST) or imported; ``before`` is its stored config when it
        already was of this kind (``None`` for a new one). Nothing to check
        by default."""
        return None

    @property
    def critical(self) -> bool:
        """Whether this input being down should degrade overall service health.

        An MQTT input is the alerting firehose (it feeds nearly every
        variable) so it defaults to critical; auxiliary http_poll / webhook
        inputs default to non-critical (a demo poller or an optional external
        feed being down must NOT make ``/v1/health`` report ``degraded`` and
        trip the operator's pipeline-down indicator / SMS watchdog).

        Override per-input via ``config: {"critical": true|false}``.
        """
        val = self.config.get("critical")
        if isinstance(val, bool):
            return val
        return self.kind == "mqtt"

    @abstractmethod
    async def start(self) -> None:
        """Begin streaming values. Must return promptly; long-running
        work goes in a background task owned by the adapter."""

    @abstractmethod
    async def stop(self) -> None:
        """Clean shutdown — cancel tasks, close sockets."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Per-adapter status snapshot. Return shape:

            {
              "connected": bool,
              "last_msg_ts": float | None,   # unix epoch
              "msg_count": int,              # since start
              "error": str | None,
            }
        """

    async def update_topics(self, topics: dict[str, Any]) -> None:
        """Default no-op. MQTT overrides to hot-swap the
        topic→variable map. ``topics`` shape is adapter-specific."""
        return None
