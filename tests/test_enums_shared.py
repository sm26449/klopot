"""The enums are defined once (app.enums) and are StrEnums.

They used to be written twice — models and API schemas — and kept in step by
hand; a value added on one side only was a silent mismatch. And as
``(str, Enum)`` their ``str()`` was ``"Severity.critical"``.
"""
from __future__ import annotations

import enum

import pytest

from app import enums
from app.db import models
from app.schemas import common

SHARED = ["ChannelKind", "InputKind", "Severity", "SnoozeScope", "SuppressedReason", "VariableSource"]
MODEL_ONLY = ["ActorKind", "DeliveryState", "DeliveryStatus"]


@pytest.mark.parametrize("name", SHARED)
def test_models_and_schemas_use_the_same_class(name):
    assert getattr(models, name) is getattr(enums, name) is getattr(common, name)


@pytest.mark.parametrize("name", SHARED + MODEL_ONLY)
def test_every_enum_is_a_strenum_whose_names_are_its_values(name):
    cls = getattr(enums, name)
    assert issubclass(cls, enum.StrEnum)
    assert all(m.name == m.value for m in cls)   # the database stores names


def test_text_is_the_value():
    assert str(enums.Severity.critical) == "critical"
    assert f"{enums.ChannelKind.telegram}" == "telegram"
    assert enums.Severity.critical == "critical"
