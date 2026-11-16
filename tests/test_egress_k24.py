"""Every outbound connection is screened, and SMTP is pinned (review K24).

- 100.100.100.200 (Alibaba Cloud's metadata service, inside 100.64.0.0/10) was
  refused only under strict egress, though safe_http documents metadata as
  always refused.
- The email channel screened the SMTP host, then let aiosmtplib resolve it
  again: a host that answers a public address to the screen and a private
  one to the connect (DNS rebinding) got through. The connection now goes to
  the screened address; TLS still validates the configured name.
- MQTT brokers (channel and input) were never screened: a broker at a
  metadata or link-local address was contacted.
"""
from __future__ import annotations

import ipaddress
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.channels import email as email_mod
from app.channels.base import Notification
from app.channels.mqtt import MQTTChannel
from app.utils.egress import screen_ip


def test_alibaba_metadata_is_always_blocked():
    assert screen_ip(ipaddress.ip_address("100.100.100.200")) is not None
    assert screen_ip(ipaddress.ip_address("100.64.0.1")) is None          # CGNAT itself: strict mode only
    assert screen_ip(ipaddress.ip_address("100.64.0.1"), block_private=True) is not None


async def test_smtp_connects_to_the_screened_address():
    sock = object()
    connect = AsyncMock(return_value=sock)
    sent = AsyncMock()
    notif = Notification(id="n", type="t", severity="warning", icon=None, title="t", message="m",
                         fired_at=datetime(2026, 11, 15, 12, 0, 0))
    config = {"smtp_host": "mail.example.com", "smtp_port": 587, "from": "a@example.com", "to": "b@example.com"}
    with patch.object(email_mod, "screen_and_pick_ip", AsyncMock(return_value="203.0.113.9")), \
            patch.object(email_mod, "_connect_pinned", connect), patch.object(email_mod.aiosmtplib, "send", sent):
        result = await email_mod.EmailChannel().send(notif, config)
    assert result.ok, result.error
    assert connect.await_args.args[:2] == ("203.0.113.9", 587)
    kwargs = sent.await_args.kwargs
    assert kwargs["sock"] is sock
    assert kwargs["hostname"] == "mail.example.com"     # SNI / certificate check on the real name
    assert kwargs.get("port") is None


async def test_an_mqtt_broker_at_a_metadata_address_is_never_contacted():
    contacted: list[str] = []

    class Client:
        def __init__(self, hostname, **_kw):
            contacted.append(hostname)

    with patch("app.channels.mqtt.broker_blocked",
               AsyncMock(return_value="blocked egress to metadata/link-local address")), \
            patch("app.channels.mqtt.aiomqtt.Client", Client):
        health = await MQTTChannel().healthcheck({"host": "169.254.169.254", "instance_id": "t"})
    assert health["reachable"] is False
    assert "metadata" in health["error"]
    assert contacted == []


async def test_broker_screen_allows_private_and_unresolvable_hosts():
    from app.utils.egress import broker_blocked

    assert await broker_blocked("172.20.0.5", 1883) is None            # the stack's own broker
    assert await broker_blocked("169.254.169.254", 1883) is not None
    assert await broker_blocked("100.100.100.200", 1883) is not None
    assert await broker_blocked("no-such-host.invalid", 1883) is None  # the client fails on its own
