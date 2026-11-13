"""F38: datetime fields must serialize as Z-suffixed UTC so a browser can't
read a next-fire / expiry / snooze instant as local time."""
from __future__ import annotations

from datetime import datetime

from app.schemas.api_key import ApiKeyRead
from app.schemas.schedule import ScheduleRead
from app.schemas.snooze import SnoozeRead
from app.schemas.variable import VariableRead

_NAIVE = datetime(2030, 1, 1, 2, 0, 0)  # naive-UTC, as stored


def test_api_key_expiry_serializes_with_z():
    m = ApiKeyRead(
        id=1, name="k", key_prefix="abcd1234", scopes=["read"], enabled=True,
        expires_at=_NAIVE, created_at=_NAIVE,
    )
    d = m.model_dump(mode="json")
    assert d["expires_at"].endswith("Z")
    assert d["created_at"].endswith("Z")


def test_schedule_next_fire_serializes_with_z():
    m = ScheduleRead(
        id=1, name="s", cron_expr="* * * * *", template_type="t",
        last_fired_at=_NAIVE, next_fire_at=_NAIVE,
        created_at=_NAIVE, updated_at=_NAIVE,
    )
    d = m.model_dump(mode="json")
    assert d["next_fire_at"].endswith("Z")


def test_snooze_until_serializes_with_z():
    m = SnoozeRead(scope="type", target="batt_low", until=_NAIVE,
                   id=1, created_at=_NAIVE)
    d = m.model_dump(mode="json")
    assert d["until"].endswith("Z")


def test_variable_last_value_at_serializes_with_z():
    m = VariableRead(
        id=1, name="v", source="mqtt", config={}, enabled=True,
        created_at=_NAIVE, updated_at=_NAIVE, last_value_at=_NAIVE,
    )
    d = m.model_dump(mode="json")
    assert d["last_value_at"].endswith("Z")
