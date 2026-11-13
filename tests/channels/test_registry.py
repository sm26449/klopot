"""Pure-unit tests for app.channels.registry — kind → adapter map."""
from __future__ import annotations

from app.channels.base import BaseChannel
from app.channels.registry import REGISTRY


def test_registry_covers_known_kinds():
    """Every documented channel kind has a class registered."""
    expected = {"ui", "banner", "telegram", "sms", "email", "push", "webhook"}
    assert expected.issubset(REGISTRY.keys())


def test_registry_classes_subclass_basechannel():
    for kind, cls in REGISTRY.items():
        assert issubclass(cls, BaseChannel), (
            f"{kind} → {cls.__name__} must subclass BaseChannel"
        )


def test_banner_aliases_ui():
    """'banner' and 'ui' use the same adapter — banners are a CSS
    presentation of the same UI WebSocket frame."""
    assert REGISTRY["banner"] is REGISTRY["ui"]
