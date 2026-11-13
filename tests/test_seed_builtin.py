"""Bootstrap-seed contract for built-in self-monitoring templates."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Channel, Template, TemplateChannel
from scripts.seed import seed_builtin_templates, seed_default_channels


async def test_seed_builtin_creates_template_and_ui_route(db_session):
    await seed_default_channels(db_session)
    created = await seed_builtin_templates(db_session)
    await db_session.commit()
    assert created == 4

    tpl = (
        await db_session.execute(
            select(Template).where(Template.type == "rule_auto_disabled")
        )
    ).scalar_one()
    assert tpl.severity.value == "warning"
    assert tpl.enabled is True
    assert "{rule_name}" in tpl.title_template

    ui = (
        await db_session.execute(select(Channel).where(Channel.name == "ui_default"))
    ).scalar_one()
    route = (
        await db_session.execute(
            select(TemplateChannel).where(
                TemplateChannel.template_id == tpl.id,
                TemplateChannel.channel_id == ui.id,
            )
        )
    ).scalar_one()
    assert route.enabled is True


async def test_seed_builtin_idempotent(db_session):
    await seed_default_channels(db_session)
    assert await seed_builtin_templates(db_session) == 4
    await db_session.commit()
    assert await seed_builtin_templates(db_session) == 0


async def test_seed_builtin_drill_templates(db_session):
    await seed_default_channels(db_session)
    await seed_builtin_templates(db_session)
    await db_session.commit()
    ok = (
        await db_session.execute(
            select(Template).where(Template.type == "restore_drill_ok")
        )
    ).scalar_one()
    failed = (
        await db_session.execute(
            select(Template).where(Template.type == "restore_drill_failed")
        )
    ).scalar_one()
    assert ok.severity.value == "info"
    assert failed.severity.value == "critical"
