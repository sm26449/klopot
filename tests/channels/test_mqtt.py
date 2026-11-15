"""Persistent publisher lifecycle and replay identity, without a live broker."""
import asyncio
import json
from datetime import datetime
from unittest.mock import patch

import aiomqtt
import pytest

from app.channels.base import Notification
from app.channels.mqtt import MQTTChannel
from app.channels.mqtt_config import validate_config


def notification(**overrides):
    fields = dict(id='ntf_mqtt', type='alarm', severity='critical', icon='!', title='A "quote"',
                  message='line\nvalue', fired_at=datetime(2026, 11, 14, 10), incident_id='inc_test')
    fields.update(overrides)
    return Notification(**fields)


class Client:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.published = []
        self.disconnected = asyncio.Event()
        self.closed = False
        self.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    @property
    def messages(self):
        async def listen():
            await self.disconnected.wait()
            raise aiomqtt.MqttError('secret broker url should not appear')
            yield  # pragma: no cover
        return listen()

    async def publish(self, topic, payload, **kwargs):
        self.published.append((topic, payload, kwargs))


@pytest.fixture
async def mqtt():
    Client.instances = []
    channel = MQTTChannel()
    with patch('app.channels.mqtt.aiomqtt.Client', Client):
        try:
            yield channel
        finally:
            await channel.close()


CONFIG = {'host': 'broker.test', '_channel_name': 'mqtt_main', 'instance_id': 'test'}


async def test_default_json_carries_stable_delivery_identity_and_no_retain(mqtt):
    for _ in range(2):
        result = await mqtt.send(notification(), CONFIG, idempotency_key='stable:delivery')
        assert result.ok
    assert len(Client.instances) == 1, 'connection reused across notifications/retries'
    client = Client.instances[0]
    messages = [p for p in client.published if p[0] == 'klopot/notifications/alarm']
    assert len(messages) == 2
    body = json.loads(messages[0][1])
    assert body['delivery_id'] == 'stable:delivery'
    assert body['incident_id'] == 'inc_test'
    assert body['title'] == 'A "quote"'
    assert body['fired_at'].endswith('Z')
    assert messages[0][2] == {'qos': 1, 'retain': False}
    assert mqtt.health_for_channel('mqtt_main')['connected']
    assert client.kwargs['will'].payload == 'offline'
    assert client.kwargs['will'].retain is True
    await mqtt.close()
    assert client.closed
    assert any(p[1] == 'offline' for p in client.published)


async def test_custom_json_cannot_remove_or_replace_delivery_id(mqtt):
    config = {**CONFIG, 'qos': 2, 'retain': True, 'payload_template': '{"text":"{title | jsonstr}","delivery_id":"wrong"}'}
    result = await mqtt.send(notification(), config, idempotency_key='stable')
    assert result.ok
    msg = next(p for p in Client.instances[0].published if p[0] == 'klopot/notifications/alarm')
    assert json.loads(msg[1]) == {'text': 'A "quote"', 'delivery_id': 'stable'}
    assert msg[2] == {'qos': 2, 'retain': True}


async def test_disconnect_reconnects_and_does_not_expose_credentials(mqtt):
    assert (await mqtt.send(notification(), CONFIG)).ok
    Client.instances[0].disconnected.set()
    for _ in range(300):
        if len(Client.instances) > 1 and mqtt.health_for_channel('mqtt_main')['connected']:
            break
        await asyncio.sleep(.01)
    assert len(Client.instances) == 2
    assert Client.instances[0].closed
    assert (await mqtt.send(notification(), CONFIG)).ok
    assert 'secret' not in str(mqtt.health_for_channel('mqtt_main'))


async def test_changed_destination_retires_old_connection(mqtt):
    assert (await mqtt.send(notification(), CONFIG)).ok
    assert (await mqtt.send(notification(), {**CONFIG, 'host': 'second.test'})).ok
    assert len(Client.instances) == 2
    assert Client.instances[0].closed
    assert Client.instances[1].kwargs['hostname'] == 'second.test'


@pytest.mark.parametrize('config', [
    {'qos': True}, {'qos': 3}, {'retain': 'false'}, {'tls': 'true'}, {'port': 0},
    {'topic_template': 'alarm/#'}, {'topic_template': 'alarm/{title}'}, {'topic_template': '{type.__class__}'},
    {'host': 'user:password@host'}, {'instance_id': 'bad/name'}, {'timeout_sec': 100},
    {'availability_topic': 'status/{id}'},
])
async def test_invalid_configuration_is_rejected_before_network(mqtt, config):
    with pytest.raises(ValueError):
        validate_config(config)
    result = await mqtt.send(notification(), {**CONFIG, **config})
    assert not result.ok
    assert Client.instances == []


async def test_rendered_wildcard_and_nonobject_payload_are_rejected(mqtt):
    assert not (await mqtt.send(notification(type='alarm/#'), CONFIG)).ok
    assert not (await mqtt.send(notification(), {**CONFIG, 'payload_template': '[]'})).ok
    assert Client.instances == []
