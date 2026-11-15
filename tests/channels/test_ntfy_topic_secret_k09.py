"""An ntfy topic is a credential (review K09).

On ntfy, whoever knows a topic name can subscribe to it and publish to it —
with no token, the name is the only protection. ``GET /v1/channels`` returned
it to any ``read`` key. It is now a write-only secret like the token, and may
come from ``topic_ref`` (an env var).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from app.channels.base import Notification
from app.channels.ntfy import NtfyChannel
from app.secrets_registry import MASK, mask_config

pytestmark = pytest.mark.anyio

TOPIC = "ops-alerts-7f3k9q2x"


def test_topic_is_masked_on_read():
    shown = mask_config("channel", "ntfy", {"server_url": "https://ntfy.sh", "topic": TOPIC})
    assert shown["topic"] == MASK
    assert shown["server_url"] == "https://ntfy.sh"


async def test_channels_api_does_not_return_the_topic(db_client, admin_key):
    r = await db_client.post("/v1/channels", headers={"X-API-Key": admin_key}, json={
        "name": "ntfy_k09", "kind": "ntfy", "config": {"topic": TOPIC}})
    assert r.status_code == 201, r.text[:200]
    listed = await db_client.get("/v1/channels", headers={"X-API-Key": admin_key})
    assert TOPIC not in listed.text


async def test_topic_from_an_env_ref_is_published_to(monkeypatch):
    monkeypatch.setenv("KLOPOT_SECRET_NTFY_TOPIC", TOPIC)
    sent: dict = {}

    async def fake_request(method, url, *, json=None, **_kw):
        sent.update(json)

        class _R:
            status_code = 200
            text = "{}"

            @staticmethod
            def json():
                return {"id": "m1"}
        return _R()

    notif = Notification(id="ntf_k09", type="t", severity="warning", icon=None, title="t", message="m",
                         fired_at=datetime(2026, 11, 15, 12, 0, 0))
    with patch("app.channels.ntfy.safe_request", new=fake_request):
        result = await NtfyChannel().send(notif, {"topic_ref": "KLOPOT_SECRET_NTFY_TOPIC"})
    assert result.ok, result.error
    assert sent["topic"] == TOPIC
