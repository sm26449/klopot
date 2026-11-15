"""Alembic environment.

Reads the database URL from the application's ``Settings`` (so we
don't duplicate env-var handling between the app and migrations).
Runs migrations in offline (SQL emit) and online (DB connect) modes.

Async note: alembic itself is sync, but our SQLAlchemy URL is the
async one (``mysql+aiomysql://``). For migrations we replace the
async driver with the sync equivalent (``aiomysql`` → ``pymysql``)
internally; production runtime keeps the async driver.

S1 has no schema yet — the autogenerate target_metadata is None.
S2 fills it via ``from app.db.base import Base`` once the models
exist.
"""
from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Make the app package importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

# Alembic Config object
config = context.config

# Override the URL with our runtime settings (lets MIGRATIONS use the
# same env vars as the app)
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.require_database_url())

# Logging — fileConfig() globally REPLACES root handlers and sets
# root level to whatever alembic.ini declares (WARNING). When the
# app spawns alembic from inside lifespan (see app/main.py), that
# clobbers our ConsoleFormatter / JsonFormatter handler and silences
# all subsequent INFO from the rule engine, scheduler, etc. Honor
# ``cfg.attributes["configure_logger"] = False`` so the caller can
# opt out without losing alembic CLI's own log config.
if config.config_file_name is not None and config.attributes.get(
    "configure_logger", True
):
    fileConfig(config.config_file_name)

# Target metadata — drives autogenerate
from app.db import Base  # noqa: E402
from app.db import models as _models  # noqa: F401, E402  (registers all tables on Base)
from app.db.migration_guard import assert_no_unapproved_downgrade  # noqa: E402

target_metadata = Base.metadata


def _install_downgrade_guard() -> None:
    """Refuse an unapproved downgrade as a GLOBAL preflight (audit V20).

    Wrap the migrations function so the computed steps are inspected before any
    of them runs; if the command is a downgrade and the operator hasn't opted in
    (ALERTD_ALLOW_DOWNGRADE), the whole command aborts before the first drop —
    not half-way through, after earlier tables are already gone. Degrades to a
    no-op if alembic's internals change, so it can never block an upgrade."""
    mc = context.get_context()
    orig_fn = getattr(mc, "_migrations_fn", None)
    if orig_fn is None:
        return

    def guarded(heads, ctx):
        steps = list(orig_fn(heads, ctx))
        assert_no_unapproved_downgrade(steps)
        return steps

    mc._migrations_fn = guarded


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emit SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    _install_downgrade_guard()
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    _install_downgrade_guard()
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Connect via async engine, run sync migrations on the connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
