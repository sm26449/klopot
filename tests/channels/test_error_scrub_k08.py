"""No stored delivery error carries the channel's own secrets (review K08).

An upstream that answers with an echo of the request — Express's
``Cannot POST /services/T0/B0/<secret>`` on a 404, a gateway quoting the token
it refused — put the webhook path or the credential into
``deliveries.last_error``, ``notifications_log.failed_channels`` and
``delivery_attempts.error``, all readable with ``read`` scope, while the
channel config itself is masked. The manager now removes the channel's secret
values and the path and query of its URLs from every error before it is kept.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from app.channels._secrets import channel_secret_strings, scrub_error
from app.channels.base import Notification, SendResult
from app.channels.manager import ChannelManager
from app.db.models import ChannelKind

pytestmark = pytest.mark.anyio

PATH_SECRET = "B0KQ7ZSECRETPATH"
URL = f"https://hooks.example.com/services/T0/{PATH_SECRET}?sig=QSIGNATURE123"
ENV_NAME = "KLOPOT_SECRET_K08C"


def test_secret_strings_cover_literals_refs_headers_and_url_parts(monkeypatch):
    monkeypatch.setenv(ENV_NAME, "env-token-123")
    cfg = {"url": URL, "auth_value_ref": ENV_NAME, "headers": {"X-Custom": "hdr-value-77"}}
    found = channel_secret_strings("webhook", cfg)
    for value in ("env-token-123", "hdr-value-77", f"/services/T0/{PATH_SECRET}", PATH_SECRET, "sig=QSIGNATURE123"):
        assert value in found, value
    assert "services" not in found          # short / generic segments stay readable


def test_scrub_error_also_removes_escaped_forms():
    text = "Illegal header value b'tok\\n123' and tok\n123 and /services/T0/" + PATH_SECRET
    out = scrub_error(text, ["tok\n123", PATH_SECRET])
    assert "123" not in out
    assert PATH_SECRET not in out


async def test_an_echoed_path_never_reaches_the_outcome(db_session, make_channel):
    mgr = ChannelManager()
    db_session.add(make_channel(kind=ChannelKind.webhook, name="hook_k08", config={"url": URL}))
    await db_session.commit()

    async def send(notif, cfg, idempotency_key=None):
        return SendResult(ok=False, error=f"HTTP 404: Cannot POST /services/T0/{PATH_SECRET}?sig=QSIGNATURE123")

    adapter = type("Adapter", (), {"send": staticmethod(send)})()
    notif = Notification(id="ntf_k08c", type="t", severity="warning", icon=None, title="t", message="m",
                         fired_at=datetime(2026, 11, 15, 12, 0, 0))
    with patch.object(mgr, "_get_adapter", return_value=adapter):
        outcome = await mgr.dispatch(notif, ["hook_k08"], db_session)
    error = outcome.failed["hook_k08"]
    assert error.startswith("HTTP 404: Cannot POST")
    assert PATH_SECRET not in error
    assert "QSIGNATURE123" not in error
