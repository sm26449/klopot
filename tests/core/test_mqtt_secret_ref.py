"""MQTT adapter resolves broker credentials via ``*_ref`` env names
(audit 2026-11-07 C-1). The connection itself is mocked: the fake
client records the kwargs it was built with, sets the adapter's stop
event and raises, so ``_run()`` exits on its first backoff wait."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.inputs.mqtt import MQTTSubscriber


class _StopNow(Exception):
    pass


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from app.config import get_settings
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("config", "env", "expected"),
    [
        (
            {"username_ref": "T_USER", "password_ref": "T_PW"},
            {"T_USER": "u1", "T_PW": "p1"},
            ("u1", "p1"),
        ),
        ({"username": "lit", "password": "litpw"}, {}, ("lit", "litpw")),
        # ref wins over literal when both present and env is set
        (
            {"username": "lit", "password": "litpw", "password_ref": "T_PW"},
            {"T_PW": "envpw"},
            ("lit", "envpw"),
        ),
        # ref set but env missing → no credentials (not the ref NAME)
        ({"password_ref": "T_MISSING"}, {}, (None, None)),
    ],
)
async def test_credentials_resolution(monkeypatch, config, env, expected):
    # *_ref resolution is default-deny (audit S-04); allowlist the test env names.
    from app.config import get_settings
    monkeypatch.setenv("ALERTD_SECRET_REF_ALLOW", "T_USER,T_PW,T_MISSING")
    get_settings.cache_clear()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("T_MISSING", raising=False)

    adapter = MQTTSubscriber(name="t", config={"host": "h", **config}, on_value=MagicMock())
    captured: dict = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        adapter._stop_evt.set()
        raise _StopNow("no broker in tests")

    with patch("app.inputs.mqtt.aiomqtt.Client", side_effect=fake_client):
        await adapter._run()

    assert (captured.get("username"), captured.get("password")) == expected
