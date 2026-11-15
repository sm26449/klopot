"""F01: a full import must not silently drop input bindings / routes.

Reproduces the production (autoflush=False) data-loss: a pack that
creates a parent (input / template / channel) and a child that
references it (variable binding / route) must materialize the binding
and the route — or fail loudly — never commit ok=true with a NULL
binding and zero routes.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Channel, Template, TemplateChannel, Variable
from app.services import config_io


_PACK = {
    "inputs": [{"name": "edge_mqtt", "kind": "mqtt", "config": {"host": "x"}}],
    "templates": [{"type": "t1", "severity": "warning", "title_template": "hi"}],
    "channels": [{"name": "ui_default", "kind": "ui"}],
    "variables": [{"name": "soc", "source": "mqtt", "input": "edge_mqtt",
                   "config": {"topic": "s/soc", "type": "number"}}],
    "routes": [{"template": "t1", "channel": "ui_default", "severity_min": "info"}],
}


async def test_full_import_materializes_binding_and_route(db_engine, db_session):
    plan = await config_io.import_config(db_session, _PACK, apply=True)
    assert plan.ok, plan.errors
    await db_session.commit()

    # Variable bound to the newly-imported input (not NULL).
    var = (
        await db_session.execute(select(Variable).where(Variable.name == "soc"))
    ).scalar_one()
    assert var.input_id is not None

    # The route exists (template t1 → channel ui_default).
    tmpl = (await db_session.execute(select(Template).where(Template.type == "t1"))).scalar_one()
    ch = (await db_session.execute(select(Channel).where(Channel.name == "ui_default"))).scalar_one()
    route = (
        await db_session.execute(
            select(TemplateChannel).where(
                TemplateChannel.template_id == tmpl.id,
                TemplateChannel.channel_id == ch.id,
            )
        )
    ).scalar_one_or_none()
    assert route is not None


async def test_unresolved_input_binding_is_a_hard_error(db_engine, db_session):
    plan = await config_io.import_config(
        db_session,
        {"variables": [{"name": "v", "source": "mqtt", "input": "nonexistent",
                        "config": {"topic": "t", "type": "number"}}]},
        apply=True,
    )
    assert not plan.ok
    assert any("nonexistent" in e for e in plan.errors)
