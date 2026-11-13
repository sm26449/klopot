"""F25/F26/F27: valid external names must not overflow identifier columns.

MySQL enforces VARCHAR lengths (error 1406) where SQLite silently truncates,
so these guards are structural (column widths vs. the schema's own max name
length) plus a pure-function test of the bounded rotation name.
"""
from __future__ import annotations

from app.api.v1.api_keys import _NAME_COL_MAX, _rotated_name
from app.db.models import ApiKey, AuditLog, NotificationLog
from app.schemas.api_key import ApiKeyCreate
from app.schemas.schedule import ScheduleCreate
from app.schemas.variable import VariableCreate


def _maxlen(model, field: str) -> int:
    return model.__table__.c[field].type.length


def _field_max(schema, field: str) -> int:
    for m in schema.model_fields[field].metadata:
        if hasattr(m, "max_length"):
            return m.max_length
    raise AssertionError(f"{schema.__name__}.{field} has no max_length")


def test_audit_resource_id_fits_longest_variable_name():
    # F25: a variable name (up to its schema max) is written to
    # audit_log.resource_id; the column must hold the full identifier.
    assert _maxlen(AuditLog, "resource_id") >= _field_max(VariableCreate, "name")


def test_notification_source_fits_schedule_origin():
    # F26: `schedule:<name>` / `test:<name>` origins; the longest prefix is
    # "schedule:" (9). The source column must hold prefix + a max-length name.
    longest_prefix = len("schedule:")
    assert _maxlen(NotificationLog, "source") >= longest_prefix + _field_max(
        ScheduleCreate, "name"
    )


def test_rotated_name_is_bounded_and_fits_column():
    long_name = "a" * _field_max(ApiKeyCreate, "name")  # a valid max-length name
    rotated = _rotated_name(long_name)
    assert len(rotated) <= _NAME_COL_MAX
    assert len(rotated) <= _maxlen(ApiKey, "name")


def test_rotated_name_strips_prior_rotation_suffix():
    once = _rotated_name("mykey")
    twice = _rotated_name(once)
    # Re-rotating does not keep growing the base.
    assert len(twice) <= _NAME_COL_MAX
    assert twice.startswith("mykey-r")
    assert once.split("-r")[0] == "mykey"


def test_rotated_name_is_collision_resistant_same_second():
    names = {_rotated_name("mykey") for _ in range(50)}
    # 16 bits of entropy per call → no collisions across 50 same-second calls.
    assert len(names) == 50
