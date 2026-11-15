"""B-13 forward fix: config-row timestamps stored and served as UTC.

Two concerns (the one-off historical repair tool is tested separately in
``test_config_timestamp_repair_b13.py``):

  1. Every DB connection forces session ``time_zone = +00:00`` on MySQL (so
     ``CURRENT_TIMESTAMP`` server defaults are stored as UTC), and leaves
     SQLite / other backends untouched.
  2. The config ``Read`` DTOs serialize timestamps as unambiguous UTC-``Z``.
"""
from __future__ import annotations

from datetime import datetime

from app.db.session import _connect_args
from app.schemas.channel import ChannelRead
from app.schemas.input import InputRead
from app.schemas.rule import RuleRead
from app.schemas.template import TemplateRead

# ── 1. Session timezone enforcement ──────────────────────────────────


def test_connect_args_forces_utc_on_mysql():
    args = _connect_args("mysql+aiomysql://u:p@h:3306/db")
    assert args == {"init_command": "SET time_zone = '+00:00'"}


def test_connect_args_empty_for_sqlite():
    assert _connect_args("sqlite+aiosqlite:///:memory:") == {}


def test_connect_args_empty_for_other_backends():
    assert _connect_args("postgresql+asyncpg://u:p@h/db") == {}


# ── 2. Serializer normalization (UTC-Z) ──────────────────────────────


def _dumped(model) -> dict:
    return model.model_dump(mode="json")


def test_channel_read_serializes_timestamps_as_utc_z():
    d = _dumped(ChannelRead(
        id=1, name="tg", kind="telegram", config={}, enabled=True,
        rate_limit_per_min=30,
        created_at=datetime(2026, 11, 12, 9, 0, 0),
        updated_at=datetime(2026, 11, 12, 10, 0, 0),
    ))
    assert d["created_at"] == "2026-11-12T09:00:00Z"
    assert d["updated_at"] == "2026-11-12T10:00:00Z"


def test_input_read_serializes_timestamps_as_utc_z():
    d = _dumped(InputRead(
        id=1, name="mq", kind="mqtt", config={}, enabled=True,
        created_at=datetime(2026, 11, 12, 9, 0, 0),
        updated_at=datetime(2026, 11, 12, 9, 30, 0),
    ))
    assert d["created_at"].endswith("Z")
    assert d["updated_at"].endswith("Z")


def test_rule_read_serializes_all_datetimes_as_utc_z():
    d = _dumped(RuleRead(
        id=1, name="r", template_type="t", condition_expr="x > 1",
        created_at=datetime(2026, 11, 12, 9, 0, 0),
        updated_at=datetime(2026, 11, 12, 9, 0, 0),
        last_evaluated_at=datetime(2026, 11, 12, 9, 5, 0),
        last_fired_at=None,
    ))
    assert d["created_at"].endswith("Z")
    assert d["updated_at"].endswith("Z")
    assert d["last_evaluated_at"].endswith("Z")
    assert d["last_fired_at"] is None  # None stays None, not "...Z"


def test_template_read_serializes_timestamps_as_utc_z():
    d = _dumped(TemplateRead(
        id=1, type="alertd_test", severity="info", title_template="T",
        created_at=datetime(2026, 11, 12, 9, 0, 0),
        updated_at=datetime(2026, 11, 12, 9, 0, 0),
    ))
    assert d["created_at"].endswith("Z")
    assert d["updated_at"].endswith("Z")
