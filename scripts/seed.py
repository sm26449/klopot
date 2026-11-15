"""Bootstrap seed for a fresh DB.

Idempotent: running multiple times never creates duplicate rows.
Called automatically on app startup (in ``app.main`` lifespan); also
runnable manually:

    docker compose exec alertd python -m scripts.seed

Seeds:
1. Default channels: ``ui_default`` (kind=ui), ``banner_default`` (kind=banner)
   if no channels exist
2. Singleton ``settings`` row with defaults if missing
3. Bootstrap admin API key if ``ALERTD_BOOTSTRAP_ADMIN_KEY`` is set
   AND ``api_keys`` table is empty
4. Built-in self-monitoring templates (``rule_auto_disabled``) —
   fired by the engine itself, must exist on every install
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from app.auth import hash_key, key_digest
from app.config import get_settings
from app.core.passwords import hash_password
from app.db import dispose_engine, init_engine
from app.db.models import (
    AdminUser,
    ApiKey,
    Channel,
    ChannelKind,
    Settings,
    Severity,
    Template,
    TemplateChannel,
)
from app.db.session import _session_factory  # noqa: F401  (initialized via init_engine)

logger = logging.getLogger(__name__)


async def seed_default_channels(session) -> int:
    """Create ``ui_default`` and ``banner_default`` if no channels exist."""
    existing = (await session.execute(select(Channel))).scalars().first()
    if existing is not None:
        return 0
    session.add_all([
        Channel(name="ui_default", kind=ChannelKind.ui, config={}),
        Channel(name="banner_default", kind=ChannelKind.banner, config={}),
    ])
    return 2


async def seed_settings(session) -> int:
    """Insert the singleton settings row if missing."""
    existing = (await session.execute(select(Settings).where(Settings.id == 1))).scalar_one_or_none()
    if existing is not None:
        return 0
    session.add(Settings(id=1))
    return 1


# 43 random URL-safe characters show ~31 distinct ones; fewer than 16 is not
# random (probability below 1e-12).
_MIN_DISTINCT_CHARS = 16


async def seed_bootstrap_admin_key(session) -> int:
    """Insert the bootstrap admin API key if conditions met."""
    settings = get_settings()
    plaintext = settings.bootstrap_admin_key.strip()
    if not plaintext:
        return 0
    if not plaintext.startswith("alertd_"):
        logger.warning(
            "ALERTD_BOOTSTRAP_ADMIN_KEY does not start with 'alertd_' — ignored"
        )
        return 0

    # A key in the generated shape is found by a fast SHA-256 digest, which is
    # only safe for a random key — what the documented generator makes. A
    # hand-made one in that shape ("alertd_aaaa…") is refused (review K25).
    if key_digest(plaintext) is not None and len(set(plaintext[len("alertd_"):])) < _MIN_DISTINCT_CHARS:
        logger.error(
            "ALERTD_BOOTSTRAP_ADMIN_KEY looks generated but is not random — ignored. Generate one with: "
            "python -c \"import secrets; print('alertd_'+secrets.token_urlsafe(32))\""
        )
        return 0

    existing_count = len((await session.execute(select(ApiKey))).scalars().all())
    if existing_count > 0:
        # Don't recreate on every startup — only on truly empty table
        return 0

    session.add(
        ApiKey(
            name="bootstrap",
            key_hash=hash_key(plaintext),
            key_prefix=plaintext[:8],
            key_digest=key_digest(plaintext),
            scopes=["admin"],
            enabled=True,
        )
    )
    logger.warning(
        "Seeded bootstrap admin API key (prefix=%s). Rotate via "
        "POST /v1/api_keys/{id}/rotate after first use.",
        plaintext[:8],
    )
    return 1


ADMIN_USERNAME = "admin"


async def seed_admin_user(session) -> int:
    """Create the single ``admin`` account on a fresh install.

    Only when ``admin_users`` is EMPTY and ``ALERTD_ADMIN_BOOTSTRAP_PASSWORD``
    is set (decision D9). The row is created with
    ``must_change_password=1`` so the bootstrap value is never the
    long-term password; clear the env var after the first login. Later
    boots are no-ops even if the variable is still present — a reset
    goes through ``python -m scripts.admin reset-password``.
    """
    settings = get_settings()
    plaintext = settings.admin_bootstrap_password
    if not plaintext:
        return 0
    existing = (await session.execute(select(AdminUser.id))).first()
    if existing is not None:
        return 0
    if len(plaintext) < 12:
        logger.warning(
            "ALERTD_ADMIN_BOOTSTRAP_PASSWORD shorter than 12 characters — ignored"
        )
        return 0
    session.add(
        AdminUser(
            username=ADMIN_USERNAME,
            password_hash=hash_password(plaintext),
            role="admin",
            is_active=True,
            must_change_password=True,
        )
    )
    logger.warning(
        "Seeded admin user %r from ALERTD_ADMIN_BOOTSTRAP_PASSWORD "
        "(must change password at first login). Clear the variable from .env now.",
        ADMIN_USERNAME,
    )
    return 1


# Built-in self-monitoring templates: the `self-monitoring` pack
# (app/packs/self-monitoring.yaml). Fired by Klopot's own machinery (engine
# meta-alerts, digest, restore drill), so they must exist on every install.
# Routed to ui_default by default; operators add other routes as usual.
def builtin_templates() -> list[dict[str, Any]]:
    from app.services import packs

    templates: list[dict[str, Any]] = packs.render(packs.catalog()["self-monitoring"]).document["templates"]
    return templates


async def seed_builtin_templates(session) -> int:
    """Insert any missing built-in templates (idempotent by type),
    each routed to ``ui_default``."""
    # Flush first so a ui_default channel just added by
    # seed_default_channels (still pending) is visible — production uses
    # autoflush=False, so without this the lookup misses it and the
    # built-in templates get no route (audit F01 class).
    await session.flush()
    ui = (
        await session.execute(select(Channel).where(Channel.name == "ui_default"))
    ).scalar_one_or_none()

    created = 0
    for spec in builtin_templates():
        existing = (
            await session.execute(
                select(Template).where(Template.type == spec["type"])
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        tpl = Template(**{**spec, "severity": Severity(spec["severity"]), "enabled": True})
        session.add(tpl)
        await session.flush()  # need tpl.id for routing
        if ui is not None:
            session.add(
                TemplateChannel(
                    template_id=tpl.id,
                    channel_id=ui.id,
                    severity_min=Severity.info,
                    enabled=True,
                )
            )
        created += 1
    return created


async def run_seed() -> dict[str, int]:
    """Run all seed steps in a single transaction. Returns counts."""
    init_engine()
    from app.db.session import _session_factory as factory  # local import

    if factory is None:
        raise RuntimeError("Session factory not initialized")

    counts = {
        "channels": 0, "settings": 0, "api_keys": 0,
        "builtin_templates": 0, "admin_users": 0,
    }
    async with factory() as session:
        async with session.begin():
            counts["channels"] = await seed_default_channels(session)
            counts["settings"] = await seed_settings(session)
            counts["api_keys"] = await seed_bootstrap_admin_key(session)
            counts["builtin_templates"] = await seed_builtin_templates(session)
            counts["admin_users"] = await seed_admin_user(session)
    return counts


async def _main() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    counts = await run_seed()
    logger.info("Seed complete: %s", counts)
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
