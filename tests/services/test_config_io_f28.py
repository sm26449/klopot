"""F28: config import must consume normalized/validated values and reject an
explicit null for a non-nullable setting instead of crashing at commit."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Channel
from app.services import config_io
from app.services.config_io import _coerce_bool


def test_coerce_bool_honours_string_false():
    # The reported bug: bool("false") is True.
    assert _coerce_bool("false", True) is False
    assert _coerce_bool("0", True) is False
    assert _coerce_bool("off", True) is False
    assert _coerce_bool("true", False) is True
    assert _coerce_bool(None, True) is True       # omitted → default
    assert _coerce_bool(None, False) is False
    assert _coerce_bool(True, False) is True
    assert _coerce_bool(0, True) is False


async def test_import_enabled_string_false_disables_channel(db_engine, db_session):
    pack = {"channels": [{"name": "ch_off", "kind": "ui", "enabled": "false"}]}
    plan = await config_io.import_config(db_session, pack, apply=True)
    assert plan.ok, plan.errors
    await db_session.commit()
    ch = (await db_session.execute(
        select(Channel).where(Channel.name == "ch_off")
    )).scalar_one()
    assert ch.enabled is False  # not wrongly enabled by bool("false")


async def test_import_null_nonnullable_setting_is_plan_error_not_crash(
    db_engine, db_session
):
    plan = await config_io.import_config(
        db_session, {"settings": {"timezone": None}}, apply=False,
    )
    assert not plan.ok
    assert any("timezone" in e and "null" in e for e in plan.errors), plan.errors
