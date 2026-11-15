"""No NaN / Infinity leaves through an aggregate or an MQTT payload (review K19).

The pre-release audit fix cleaned non-finite numbers where values come in. Arithmetic after
intake made them again: an aggregate ``sum`` of two 1e308 readings is ``inf``,
which reached the state cache, ``/v1/state`` (a 500: the JSON encoder refuses
it) and the admin UI's live frames (``JSON.parse`` throws). An MQTT
``payload_template`` that renders ``NaN`` was re-emitted as the invalid JSON
literal ``NaN`` to every subscriber.
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.base import Notification
from app.channels.mqtt import MQTTChannel
from app.core.variable_resolver import _aggregate

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("op", ["sum", "avg"])
def test_an_overflowing_aggregate_is_none(op):
    assert _aggregate([1e308, 1e308], op) is None


def test_finite_aggregates_are_unchanged():
    assert _aggregate([1, 2, 3], "sum") == 6
    assert _aggregate([1.5, 2.5], "avg") == 2.0
    assert _aggregate([1e308, 1e308], "max") == 1e308


async def test_an_mqtt_payload_never_carries_nan():
    published: list[str] = []
    publisher = AsyncMock()
    publisher.publish = AsyncMock(side_effect=lambda topic, payload, qos, retain: published.append(payload))
    notif = Notification(id="ntf_k19", type="t", severity="warning", icon=None, title="t", message="m",
                         fired_at=datetime(2026, 11, 15, 12, 0, 0))
    config = {"topic_template": "klopot/{type}", "payload_template": '{"value": NaN, "big": Infinity, "t": "{title}"}',
              "_channel_name": "mq", "instance_id": "test", "host": "broker.test"}
    with patch.object(MQTTChannel, "_publisher", AsyncMock(return_value=publisher)):
        result = await MQTTChannel().send(notif, config, idempotency_key="ntf_k19:mq")
    assert result.ok, result.error
    body = json.loads(published[0], parse_constant=lambda name: pytest.fail(f"{name} in the payload"))
    assert body["value"] is None
    assert body["big"] is None
