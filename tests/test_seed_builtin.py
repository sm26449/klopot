"""Bootstrap-seed contract for built-in self-monitoring templates."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Channel, Template, TemplateChannel
from scripts.seed import builtin_templates, seed_builtin_templates, seed_default_channels

BUILT_IN = len(builtin_templates())


async def test_seed_builtin_creates_template_and_ui_route(db_session):
    await seed_default_channels(db_session)
    created = await seed_builtin_templates(db_session)
    await db_session.commit()
    assert created == BUILT_IN == 8

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
    assert await seed_builtin_templates(db_session) == BUILT_IN
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


async def test_an_existing_install_gets_the_new_built_in_templates_on_start(db_session):
    # 1.3.0 adds the Kurier watchdog templates: an install seeded by an older
    # release (the first four) gets them at the next start, its own edits kept.
    await seed_default_channels(db_session)
    first_four = {"rule_auto_disabled", "restore_drill_ok", "daily_suppressed_digest", "restore_drill_failed"}
    for spec in builtin_templates():
        if spec["type"] in first_four:
            db_session.add(Template(**{**spec, "title_template": "edited by the operator"}))
    await db_session.commit()
    assert await seed_builtin_templates(db_session) == 4
    await db_session.commit()
    types = set((await db_session.execute(select(Template.type))).scalars())
    assert {"kurier_unreachable", "kurier_reachable", "kurier_modem_down", "kurier_modem_up"} <= types
    kept = (await db_session.execute(select(Template).where(Template.type == "rule_auto_disabled"))).scalar_one()
    assert kept.title_template == "edited by the operator"
