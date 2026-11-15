"""D1-02: MQTT ingress must be bounded and scoped.

- The incoming queue is given a finite capacity.
- The adapter subscribes to the configured filters, never ``#``.
- Oversized payloads are dropped (and counted) before decode.
- Filter updates subscribe new topics and unsubscribe removed ones.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import get_settings
from app.inputs.mqtt import MQTTSubscriber

pytestmark = pytest.mark.anyio


async def _noop(topic, payload, source_kind):  # pragma: no cover - replaced per test
    ...


def _adapter(on_value=None):
    return MQTTSubscriber(name="t", config={"host": "h"}, on_value=on_value or _noop)


def _msg(topic: str, payload):
    return SimpleNamespace(topic=topic, payload=payload)


class _FakeClient:
    """Stand-in for aiomqtt.Client capturing (un)subscribes."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def subscribe(self, topic, qos=0):
        self.subscribed.append(topic)

    async def unsubscribe(self, topic):
        self.unsubscribed.append(topic)


# ── Byte cap ─────────────────────────────────────────────────────────


async def test_oversized_payload_is_dropped_and_counted():
    seen = AsyncMock()
    a = _adapter(on_value=seen)
    a._exact_filter = {"t/x"}
    big = b"x" * (get_settings().mqtt_max_payload_bytes + 1)
    await a._on_message(_msg("t/x", big))
    seen.assert_not_called()
    assert a.health()["dropped_oversized"] == 1
    assert a.health()["msg_count"] == 0


async def test_normal_payload_is_processed():
    seen = AsyncMock()
    a = _adapter(on_value=seen)
    a._exact_filter = {"t/x"}
    await a._on_message(_msg("t/x", b'{"v": 1}'))
    seen.assert_awaited_once()
    topic, payload, kind = seen.await_args.args
    assert (topic, payload, kind) == ("t/x", {"v": 1}, "mqtt")
    assert a.health()["dropped_oversized"] == 0
    assert a.health()["msg_count"] == 1


async def test_uninteresting_topic_ignored_before_byte_check():
    seen = AsyncMock()
    a = _adapter(on_value=seen)
    a._exact_filter = {"t/x"}
    await a._on_message(_msg("other/topic", b"anything"))
    seen.assert_not_called()
    assert a.health()["msg_count"] == 0


# ── Subscription model: configured filters, bounded queue, never '#' ──


async def test_connect_subscribes_to_filters_not_hash(monkeypatch):
    a = _adapter()
    a._exact_filter = {"a/b"}
    a._wildcard_filter = {"c/+"}
    created: dict[str, object] = {}

    class _ConnClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.subscribed: list[str] = []
            created["client"] = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def subscribe(self, topic, qos=0):
            self.subscribed.append(topic)

        @property
        def messages(self):
            # An empty stream that ends the loop immediately and stops _run's
            # reconnect while-loop, so the test returns after one connect.
            async def gen():
                a._stop_evt.set()
                return
                yield  # pragma: no cover
            return gen()

    monkeypatch.setattr("app.inputs.mqtt.aiomqtt.Client", _ConnClient)
    await a._run()

    client = created["client"]
    assert set(client.subscribed) == {"a/b", "c/+"}
    assert "#" not in client.subscribed
    assert client.kwargs["max_queued_incoming_messages"] == get_settings().mqtt_queue_max


# ── Filter updates subscribe new, unsubscribe removed ────────────────


async def test_update_topics_subscribes_new_and_unsubscribes_removed():
    a = _adapter()
    client = _FakeClient()
    a._client = client

    await a.update_topics({"exact": {"a", "b"}, "wildcard": set()})
    assert set(client.subscribed) == {"a", "b"}
    assert client.unsubscribed == []

    client.subscribed.clear()
    await a.update_topics({"exact": {"b", "c"}, "wildcard": set()})
    assert set(client.subscribed) == {"c"}        # only the newly added
    assert set(client.unsubscribed) == {"a"}      # the removed one dropped
