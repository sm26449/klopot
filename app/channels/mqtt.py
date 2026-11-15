"""Persistent MQTT output; the durable outbox remains the retry authority."""
from __future__ import annotations

import asyncio
import hashlib
import json
import ssl
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Any

import aiomqtt

from ..core import rendering
from ..metrics import ENGINE_LAST_TICK
from ..utils.egress import broker_blocked
from ._secrets import resolve_secret
from .base import BaseChannel, Notification, SendResult
from .mqtt_config import freeze_defaults, validate_config, validate_topic


class _BrokerBlocked(Exception):
    """The broker's address is never a legitimate target (review K24)."""


@dataclass
class _Request:
    topic: str
    payload: str
    qos: int
    retain: bool
    future: asyncio.Future[None]


class _Publisher:
    def __init__(self, config: dict[str, Any], name: str, username: str | None, password: str | None) -> None:
        self.config = config
        self.name = name
        self.username = username
        self.password = password
        self.connected = False
        self.error: str | None = None
        self.last_publish: float | None = None
        self.queue: asyncio.Queue[_Request] = asyncio.Queue(maxsize=100)
        self.task = asyncio.create_task(self._run(), name="mqtt-output")

    def topic(self, key: str, default: str) -> str:
        template = self.config.get(key, default)
        if not template:
            return ""
        result = str(template).format_map({"instance": self.config.get("instance_id", "alertd"), "channel": self.name})
        validate_topic(result)
        return result

    async def publish(self, topic: str, payload: str, qos: int, retain: bool) -> None:
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        request = _Request(topic, payload, qos, retain, future)
        try:
            self.queue.put_nowait(request)
        except asyncio.QueueFull:
            raise aiomqtt.MqttError("MQTT output queue full") from None
        await future

    async def _serve(self, client: aiomqtt.Client) -> None:
        while True:
            request = await self.queue.get()
            if request.future.cancelled():
                continue
            try:
                await client.publish(request.topic, request.payload, qos=request.qos, retain=request.retain)
                self.last_publish = time.time()
                if not request.future.done():
                    request.future.set_result(None)
            finally:
                if not request.future.done():
                    request.future.set_exception(aiomqtt.MqttError("MQTT publish interrupted"))

    async def _watch(self, client: aiomqtt.Client) -> None:
        async for _ in client.messages:
            pass  # no subscriptions; iteration observes broker disconnects
        raise aiomqtt.MqttError("MQTT disconnected")

    async def _heartbeat(self, client: aiomqtt.Client) -> None:
        topic = self.topic("heartbeat_topic", "klopot/{instance}/outputs/{channel}/heartbeat")
        while True:
            if topic:
                payload = json.dumps({"timestamp": time.time(), "engine_last_tick_timestamp": ENGINE_LAST_TICK._value.get()})
                await client.publish(topic, payload, qos=0, retain=False)
            await asyncio.sleep(30)

    async def _run(self) -> None:
        delay = 1.0
        status_topic = self.topic("availability_topic", "klopot/{instance}/outputs/{channel}/status")
        while True:
            try:
                blocked = await broker_blocked(self.config["host"], self.config["port"])
                if blocked:
                    raise _BrokerBlocked(blocked)
                async with aiomqtt.Client(
                    hostname=self.config["host"], port=self.config["port"], username=self.username, password=self.password,
                    identifier=f"klopot-out-{uuid.uuid4().hex[:20]}", timeout=self.config.get("timeout_sec", 10),
                    max_queued_incoming_messages=1, max_queued_outgoing_messages=100,
                    will=aiomqtt.Will(status_topic, "offline", qos=1, retain=True) if status_topic else None,
                    tls_context=ssl.create_default_context() if self.config.get("tls") else None,
                ) as client:
                    if status_topic:
                        await client.publish(status_topic, "online", qos=1, retain=True)
                    self.connected, self.error = True, None
                    delay = 1.0
                    try:
                        async with asyncio.TaskGroup() as tasks:
                            tasks.create_task(self._serve(client))
                            tasks.create_task(self._watch(client))
                            tasks.create_task(self._heartbeat(client))
                    finally:
                        if status_topic:
                            try:
                                async with asyncio.timeout(2):
                                    await client.publish(status_topic, "offline", qos=1, retain=True)
                            except Exception:
                                pass
            except asyncio.CancelledError:
                raise
            except _BrokerBlocked as e:
                self.error = str(e)
            except Exception:
                # Broker exceptions can contain credentials. Store no raw text.
                self.error = "MQTT connection or publish failed"
            finally:
                self.connected = False
                while not self.queue.empty():
                    request = self.queue.get_nowait()
                    if not request.future.done():
                        request.future.set_exception(aiomqtt.MqttError("MQTT connection unavailable"))
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def close(self) -> None:
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


class MQTTChannel(BaseChannel):
    kind = "mqtt"

    def __init__(self) -> None:
        self._publishers: OrderedDict[str, _Publisher] = OrderedDict()
        self._lock = asyncio.Lock()

    async def _publisher(self, config: dict[str, Any]) -> _Publisher:
        username = resolve_secret(config, "username", "username_ref")
        password = resolve_secret(config, "password", "password_ref")
        # Bound the cache, including retired configurations. Keys are never exposed.
        key = hashlib.sha256(json.dumps([config, username, password], sort_keys=True, default=str).encode()).hexdigest()
        async with self._lock:
            existing = self._publishers.get(key)
            if existing is not None and not existing.task.done():
                self._publishers.move_to_end(key)
                return existing
            if existing is not None:
                await self._publishers.pop(key).close()
            name = str(config.get("_channel_name", "mqtt"))
            for retired_key, retired in list(self._publishers.items()):
                if retired.name == name:
                    await self._publishers.pop(retired_key).close()
            if len(self._publishers) >= 32:
                _, retired = self._publishers.popitem(last=False)
                await retired.close()
            publisher = _Publisher(config, str(config.get("_channel_name", "mqtt")), username, password)
            self._publishers[key] = publisher
            return publisher

    async def send(self, notif: Notification, config: dict[str, Any], *, idempotency_key: str | None = None) -> SendResult:
        try:
            config = freeze_defaults(config)
            validate_config(config)
            context = {**(notif.vars_payload or {}), **asdict(notif), "instance": config["instance_id"],
                       "channel": config.get("_channel_name", "mqtt"), "delivery_id": idempotency_key or notif.id}
            context["fired_at"] = notif.fired_at.isoformat() + ("Z" if notif.fired_at.tzinfo is None else "")
            topic = config.get("topic_template", "klopot/notifications/{type}").format_map(context)
            validate_topic(topic)
            for field, default in (("availability_topic", "klopot/{instance}/outputs/{channel}/status"),
                                   ("heartbeat_topic", "klopot/{instance}/outputs/{channel}/heartbeat")):
                template = config.get(field, default)
                if template:
                    validate_topic(template.format_map(context))
            template = config.get("payload_template")
            if template:
                payload = rendering.render(template, context)
                # NaN / Infinity are not JSON: never re-emit them (review K19).
                body = json.loads(payload, parse_constant=lambda _name: None)
                if not isinstance(body, dict):
                    raise ValueError("MQTT payload_template must render a JSON object")
                # Custom payloads also carry a stable identity for outbox replays.
                body["delivery_id"] = context["delivery_id"]
            else:
                body = asdict(notif)
                body.update(fired_at=context["fired_at"], delivery_id=context["delivery_id"])
            payload = json.dumps(body, ensure_ascii=False, default=str, allow_nan=False)
            if len(payload.encode()) > 262144:
                raise ValueError("MQTT payload exceeds 256 KiB")
            async with asyncio.timeout(config.get("timeout_sec", 10)):
                publisher = await self._publisher(config)
                await publisher.publish(topic, payload, config.get("qos", 1), config.get("retain", False))
            return SendResult(ok=True)
        except (ValueError, KeyError, TypeError):
            return SendResult(ok=False, error="MQTT invalid configuration, topic or JSON payload")
        except (TimeoutError, aiomqtt.MqttError):
            return SendResult(ok=False, error="MQTT publish unavailable or timed out")

    def health_for_channel(self, name: str) -> dict[str, Any]:
        matches = [p for p in self._publishers.values() if p.name == name]
        publisher = matches[-1] if matches else None
        return {"attempted": publisher is not None, "connected": bool(publisher and publisher.connected),
                "error": publisher.error if publisher else None,
                "last_publish_ts": publisher.last_publish if publisher else None}

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        try:
            config = freeze_defaults(config)
            validate_config(config)
            blocked = await broker_blocked(config["host"], config["port"])
            if blocked:
                return {"reachable": False, "error": blocked}
            async with asyncio.timeout(5):
                async with aiomqtt.Client(hostname=config["host"], port=config["port"],
                    username=resolve_secret(config, "username", "username_ref"),
                    password=resolve_secret(config, "password", "password_ref"),
                    tls_context=ssl.create_default_context() if config.get("tls") else None,
                    timeout=5):
                    return {"reachable": True}
        except Exception:
            return {"reachable": False, "error": "MQTT broker unavailable or invalid configuration"}

    async def close(self) -> None:
        async with self._lock:
            await asyncio.gather(*(p.close() for p in self._publishers.values()))
            self._publishers.clear()
