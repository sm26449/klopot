"""V02: re-applying a MASKED export must not destroy a route's secret.

A masked export rewrites secret-looking values (e.g. a route override's
``auth_value``) to ``env:UNKNOWN_*`` placeholders. ``_import_inputs`` and
``_import_channels`` run every imported config through the import sanitizer
so a placeholder keeps the live secret; ``_import_routes`` did not, so
re-importing a masked export wrote the placeholder literally over the live
credential — a config/credential loss that silently breaks delivery.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Channel, ChannelKind, Severity, Template, TemplateChannel
from app.services import config_io


async def test_masked_route_export_reimport_destroys_secret(
    db_engine, db_session, make_template, make_channel
):
    t = make_template()
    c = make_channel(kind=ChannelKind.webhook, config={"url": "https://x/hook"})
    db_session.add_all([t, c])
    await db_session.flush()
    db_session.add(TemplateChannel(
        template_id=t.id, channel_id=c.id,
        severity_min=Severity.info, enabled=True,
        channel_overrides={"auth_value": "fake-verify-secret"},
    ))
    await db_session.commit()

    # Export with masking, as the "safe sharing" export does.
    masked = await config_io.export_config(db_session, mask_secrets=True)
    route = next(r for r in masked["routes"] if r["template"] == t.type)
    assert route["channel_overrides"]["auth_value"] == "env:UNKNOWN_AUTH_VALUE"

    # Re-apply that masked export.
    plan = await config_io.import_config(db_session, masked, apply=True)
    assert plan.ok, plan.errors
    await db_session.commit()

    # The live route secret must survive — the placeholder must NOT clobber it.
    tc = (await db_session.execute(
        select(TemplateChannel)
        .join(Template, Template.id == TemplateChannel.template_id)
        .join(Channel, Channel.id == TemplateChannel.channel_id)
        .where(Template.type == t.type, Channel.name == c.name)
    )).scalar_one()
    assert tc.channel_overrides["auth_value"] == "fake-verify-secret", (
        "masked placeholder overwrote the live route secret"
    )
