"""A14: config export/import completeness + masked-secret safety."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Channel, ChannelKind, Template
from app.services import config_io


async def test_category_round_trips(db_engine, db_session, make_template):
    t = make_template(type="catt", category="Battery")
    db_session.add(t)
    await db_session.commit()

    exported = await config_io.export_config(db_session)
    tmpl = next(x for x in exported["templates"] if x["type"] == "catt")
    assert tmpl["category"] == "Battery"   # was dropped before A14

    # And import restores it.
    await config_io.import_config(db_session, {
        "templates": [{
            "type": "catt2", "severity": "info",
            "title_template": "hi", "category": "Grid",
        }],
    }, apply=True)
    await db_session.commit()
    row = (
        await db_session.execute(select(Template).where(Template.type == "catt2"))
    ).scalar_one()
    assert row.category == "Grid"


async def test_masked_placeholder_does_not_clobber_secret(
    db_engine, db_session, make_channel
):
    c = make_channel(
        name="a14c", kind=ChannelKind.webhook,
        config={"url": "https://x", "password": "realsecret"},
    )
    db_session.add(c)
    await db_session.commit()

    # Re-import a MASKED export of the same channel.
    plan = await config_io.import_config(db_session, {
        "channels": [{
            "name": "a14c", "kind": "webhook",
            "config": {"url": "https://x", "password": "env:UNKNOWN_PASSWORD"},
        }],
    }, apply=True)
    await db_session.commit()

    row = (
        await db_session.execute(select(Channel).where(Channel.name == "a14c"))
    ).scalar_one()
    assert row.config["password"] == "realsecret"  # live secret kept
    assert any("masked placeholder" in w for w in plan.warnings)


async def test_masked_placeholder_nested_header_kept(
    db_engine, db_session, make_channel
):
    c = make_channel(
        name="a14h", kind=ChannelKind.webhook,
        config={"url": "https://x", "headers": {"Authorization": "Bearer real"}},
    )
    db_session.add(c)
    await db_session.commit()

    await config_io.import_config(db_session, {
        "channels": [{
            "name": "a14h", "kind": "webhook",
            "config": {"url": "https://x",
                       "headers": {"Authorization": "env:UNKNOWN_AUTHORIZATION"}},
        }],
    }, apply=True)
    await db_session.commit()

    row = (
        await db_session.execute(select(Channel).where(Channel.name == "a14h"))
    ).scalar_one()
    assert row.config["headers"]["Authorization"] == "Bearer real"


async def test_settings_import_warns_not_fully_restorable(db_engine, db_session):
    plan = await config_io.import_config(
        db_session, {"settings": {"log_retention_days": 30}}, apply=False,
    )
    assert any("environment" in w for w in plan.warnings)
