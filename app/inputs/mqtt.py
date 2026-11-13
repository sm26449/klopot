"""MQTT input adapter — subscribe to the configured topic filters.

The adapter subscribes to the union of each declared variable's exact and
wildcard topics (not ``#``) so unrelated traffic never enters the incoming
queue (audit D1-02), and still filters in-process as a cheap second check.
The queue itself is bounded (``mqtt_queue_max``) and oversized payloads are
dropped (``mqtt_max_payload_bytes``), so neither a broad retained flood nor a
burst can grow memory without limit.

Hot reload: ``update_topics(set_of_topics)`` adds subscriptions for newly
declared topics (which also triggers retained redelivery) and unsubscribes
ones no longer referenced.

Resilience: aiomqtt re-establishes the connection automatically when the
broker drops. We log connect/disconnect transitions and keep the adapter
alive across them.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiomqtt

from ..config import get_settings
from ._secrets_helper import resolve_secret_local
from .base import BaseInput, ValueCallback

logger = logging.getLogger(__name__)


class MQTTSubscriber(BaseInput):
    """One persistent connection per declared MQTT input."""

    kind = "mqtt"

    def __init__(self, *, name: str, config: dict[str, Any], on_value: ValueCallback) -> None:
        super().__init__(name=name, config=config, on_value=on_value)
        self._task: asyncio.Task[None] | None = None
        self._stop_evt: asyncio.Event = asyncio.Event()

        # Filter: set of exact topics we care about. Empty = drop all
        # (until update_topics is called). Wildcard topics (with + or
        # #) go in _wildcard_filter for fallback matching.
        self._exact_filter: set[str] = set()
        self._wildcard_filter: set[str] = set()

        # Live aiomqtt client handle. Set inside _run while connected,
        # cleared on disconnect. update_topics() reads it to issue
        # explicit per-topic subscribes for newly-added vars, which
        # triggers broker-side retained-message redelivery (audit C-4).
        self._client: aiomqtt.Client | None = None

        # Health
        self._connected: bool = False
        self._last_msg_ts: float | None = None
        self._msg_count: int = 0
        self._last_error: str | None = None
        # Count of messages dropped before decode for exceeding the payload
        # byte cap (audit D1-02). Surfaced in health.
        self._dropped_oversized: int = 0

    # ── BaseInput surface ───────────────────────────────────────────

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run(), name=f"mqtt-{self.name}")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def health(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "last_msg_ts": self._last_msg_ts,
            "msg_count": self._msg_count,
            "dropped_oversized": self._dropped_oversized,
            "error": self._last_error,
        }

    async def update_topics(self, topics: dict[str, Any]) -> None:
        """Update the filter set, subscribing to newly-declared topics and
        unsubscribing from ones no longer referenced.

        ``topics`` shape: ``{"exact": set[str], "wildcard": set[str]}``.

        The adapter subscribes to the configured filters (not ``#``, audit
        D1-02), so adding a variable needs an explicit SUBSCRIBE — which also
        makes the broker redeliver that topic's retained value (MQTT 3.1.1
        §3.8.4), fixing the retained-and-quiet case (e.g.
        ``site/controller/enabled`` = "true", published once at boot,
        would otherwise stay ``None`` forever). Removing a variable's topic
        unsubscribes it so its traffic stops entering the bounded queue.
        """
        exact = set(topics.get("exact", set()))
        wildcard = set(topics.get("wildcard", set()))
        new_exact = exact - self._exact_filter
        new_wildcard = wildcard - self._wildcard_filter
        removed = (self._exact_filter | self._wildcard_filter) - (exact | wildcard)
        self._exact_filter = exact
        self._wildcard_filter = wildcard
        logger.info(
            "MQTT %s topic filter updated: %d exact, %d wildcard "
            "(+%d/-%d since last update)",
            self.name, len(self._exact_filter), len(self._wildcard_filter),
            len(new_exact) + len(new_wildcard), len(removed),
        )

        # Apply the delta to the live subscription. Safe no-op if we're not
        # currently connected — the next reconnect subscribes the full filter
        # set (and so redelivers retained) from scratch.
        client = self._client
        if client is None:
            return
        for topic in sorted(new_exact | new_wildcard):
            try:
                await client.subscribe(topic, qos=0)
                logger.debug("MQTT %s subscribed to %s (retained kick)",
                             self.name, topic)
            except Exception as e:
                # Don't fail the whole update if one subscribe errors; others
                # still apply and the in-memory filter is already in place.
                logger.warning("MQTT %s subscribe %s failed: %s",
                               self.name, topic, e)
        for topic in sorted(removed):
            try:
                await client.unsubscribe(topic)
                logger.debug("MQTT %s unsubscribed from %s", self.name, topic)
            except Exception as e:
                logger.warning("MQTT %s unsubscribe %s failed: %s",
                               self.name, topic, e)

    # ── Internals ───────────────────────────────────────────────────

    async def _run(self) -> None:
        """Long-running task. Reconnects on disconnect with backoff."""
        host = self.config.get("host", "localhost")
        port = int(self.config.get("port", 1883))
        # Credentials via ``*_ref`` (env var name) first, literal second —
        # same contract as every other adapter (audit 2026-11-07 C-1;
        # before this the broker password could only be stored in clear).
        username = resolve_secret_local(self.config, "username", "username_ref")
        password = resolve_secret_local(self.config, "password", "password_ref")
        client_id = self.config.get("client_id") or f"alertd-{self.name}"
        keepalive = int(self.config.get("keepalive", 60))

        backoff = 1.0
        while not self._stop_evt.is_set():
            try:
                logger.info("MQTT %s connecting to %s:%d", self.name, host, port)
                async with aiomqtt.Client(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    identifier=client_id,
                    keepalive=keepalive,
                    # Bound the incoming queue (audit D1-02): aiomqtt defaults
                    # to unbounded, so a publisher or retained burst could grow
                    # memory without limit. On overflow aiomqtt drops (QoS0); a
                    # missed update degrades to staleness and the re-subscribes
                    # below redeliver retained state.
                    max_queued_incoming_messages=get_settings().mqtt_queue_max,
                ) as client:
                    self._client = client
                    self._connected = True
                    self._last_error = None
                    backoff = 1.0
                    # Subscribe to the configured filters only (audit D1-02),
                    # never '#': unrelated topics must not enter the bounded
                    # queue. Each subscribe is also spec-guaranteed retained
                    # redelivery (MQTT 3.1.1 §3.8.4), which fixes the retained-
                    # only quiet-topic case (observed 2026-07-15: a dead field
                    # device's offline value must land, not stay None forever).
                    filters = sorted(self._exact_filter | self._wildcard_filter)
                    logger.info(
                        "MQTT %s connected, subscribing to %d filter(s)",
                        self.name, len(filters),
                    )
                    for _topic in filters:
                        try:
                            await client.subscribe(_topic, qos=0)
                        except Exception as e:
                            logger.warning("MQTT %s subscribe %s failed: %s",
                                           self.name, _topic, e)
                    try:
                        async for message in client.messages:
                            await self._on_message(message)
                            if self._stop_evt.is_set():
                                break
                    finally:
                        # Clear the live client handle as soon as we
                        # leave the message loop, before the async-with
                        # actually tears down the connection. Prevents
                        # update_topics() from calling subscribe() on
                        # a half-closed client.
                        self._client = None
            except asyncio.CancelledError:
                self._client = None
                self._connected = False
                raise
            except Exception as e:
                self._client = None
                self._connected = False
                # Category only in the stored error — the broker exception
                # string can carry the connection URL/credentials. The full
                # detail stays in debug logs (audit A-07).
                self._last_error = type(e).__name__
                logger.warning(
                    "MQTT %s disconnected: %s — reconnecting in %.1fs",
                    self.name, type(e).__name__, backoff,
                )
                logger.debug("MQTT %s disconnect detail: %s", self.name, e)
                # Wait with cancellation responsiveness
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=backoff)
                    return  # stop event fired during backoff
                except TimeoutError:
                    pass
                backoff = min(backoff * 2, 60.0)

        self._connected = False

    async def _on_message(self, msg: aiomqtt.Message) -> None:
        """Filter against declared topics; dispatch to on_value."""
        topic = str(msg.topic)
        if not self._is_interesting(topic):
            return
        # Drop an oversized payload before decode (audit D1-02): one huge
        # message must not be decoded/parsed into memory.
        payload_raw = msg.payload
        max_bytes = get_settings().mqtt_max_payload_bytes
        if isinstance(payload_raw, bytes | bytearray | str) and len(payload_raw) > max_bytes:
            self._dropped_oversized += 1
            logger.warning(
                "MQTT %s dropped oversized payload on %s (%d > %d bytes)",
                self.name, topic, len(payload_raw), max_bytes,
            )
            return
        self._msg_count += 1
        self._last_msg_ts = time.time()

        # Decode payload — try JSON first, fall back to text/bytes.
        payload: Any = msg.payload
        if isinstance(payload, bytes):
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text is not None:
                # Try JSON
                try:
                    payload = json.loads(text)
                except (ValueError, json.JSONDecodeError):
                    payload = text

        try:
            await self.on_value(topic, payload, "mqtt")
        except Exception:
            logger.exception("on_value handler raised for topic=%s", topic)

    def _is_interesting(self, topic: str) -> bool:
        """O(1) exact lookup, O(n) wildcard fallback (small n)."""
        if topic in self._exact_filter:
            return True
        if self._wildcard_filter:
            for pattern in self._wildcard_filter:
                if _topic_matches(pattern, topic):
                    return True
        return False


def _topic_matches(pattern: str, topic: str) -> bool:
    """MQTT-style topic match. ``+`` = single level, ``#`` = remainder.

    Implementing inline (vs paho.topic_matches_sub) so we don't need
    paho as a runtime dep alongside aiomqtt.
    """
    p_parts = pattern.split("/")
    t_parts = topic.split("/")
    i = 0
    for p in p_parts:
        if p == "#":
            return True  # match remainder
        if i >= len(t_parts):
            return False
        if p == "+" or p == t_parts[i]:
            i += 1
            continue
        return False
    return i == len(t_parts)
