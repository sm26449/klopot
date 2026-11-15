"""Unit tests for input criticality (BaseInput.critical).

Drives the /v1/health overall-status weighting: only critical inputs may
degrade the service. A non-critical input down (a demo poller, an optional
external feed) must NOT report degraded — that previously tripped the
downstream "alert pipeline DOWN" indicator and SMS watchdog on a dead
httpbin demo poller (regression fixed 2026-06-16).
"""
from __future__ import annotations

from typing import Any

from app.inputs.base import BaseInput


class _Dummy(BaseInput):
    kind = "base"

    async def start(self) -> None:  # pragma: no cover - not exercised
        ...

    async def stop(self) -> None:  # pragma: no cover
        ...

    def health(self) -> dict[str, Any]:  # pragma: no cover
        return {}


async def _noop(topic: str, payload: Any, source_kind: str) -> None:  # pragma: no cover
    ...


def _make(kind: str, config: dict[str, Any] | None = None) -> _Dummy:
    a = _Dummy(name="t", config=config or {}, on_value=_noop)
    a.kind = kind
    return a


def test_mqtt_input_is_critical_by_default() -> None:
    # The MQTT firehose feeds nearly every variable → critical.
    assert _make("mqtt").critical is True


def test_http_poll_and_webhook_default_non_critical() -> None:
    # Auxiliary feeds — their loss must not degrade overall health.
    assert _make("http_poll").critical is False
    assert _make("webhook").critical is False


def test_explicit_config_overrides_default() -> None:
    # An operator can promote an optional feed to critical, or demote MQTT.
    assert _make("http_poll", {"critical": True}).critical is True
    assert _make("mqtt", {"critical": False}).critical is False


def test_non_bool_critical_falls_back_to_kind_default() -> None:
    # A junk value must not silently flip behaviour.
    assert _make("mqtt", {"critical": "yes"}).critical is True
    assert _make("http_poll", {"critical": 1}).critical is False
