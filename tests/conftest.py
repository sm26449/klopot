"""Shared pytest fixtures.

Two layers of fixtures:

- **Pure-unit layer** (``client``): in-process FastAPI app via
  ASGITransport. No DB, no MQTT, no scheduled tasks.
- **DB layer** (``db_engine``, ``db_session``, ``db_app`` +
  ``db_client``): in-memory SQLite (aiosqlite driver) with the
  full ORM schema created via ``Base.metadata.create_all``. Bypasses
  Alembic — the migrations are MySQL-specific in places.

The DB-backed fixtures patch ``app.db.session._engine`` and
``_session_factory`` so any code path that reaches for
``get_session_factory()`` finds the SQLite test DB instead of
trying to connect to MySQL.

We override ``ALERTD_BOOTSTRAP_ADMIN_KEY`` for the duration of each
test so the seed routine plants a known key the smoke tests can use.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# Test-friendly env BEFORE any app module is imported. ALERTD_DATABASE_URL
# is set so any accidental engine init in a test happens against SQLite,
# not MySQL.
os.environ.setdefault("ALERTD_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ALERTD_MQTT_HOST", "")  # disables MQTT input
os.environ.setdefault("ALERTD_BOOTSTRAP_ADMIN_KEY", "alertd_test_key")
os.environ.setdefault("ALERTD_LOG_LEVEL", "WARNING")
# httpx's cookie jar honours the Secure flag — the test base_url is
# plain http, so session cookies must be issued without it.
os.environ.setdefault("ALERTD_COOKIE_SECURE", "false")

# Optionally run the DB-backed fixtures against a real MySQL instead of the
# in-memory SQLite, for the transaction-semantics tests that need MySQL
# locking/isolation and the MySQL-specific upsert paths (audit V03-V06). Unset
# → unchanged in-memory SQLite. Use a THROWAWAY database: the fixture drops and
# recreates the whole schema per test. Intended for running the transactional
# subset in its own process; mixing with SQLite tests in one run is not
# supported (the SQLite branch coerces BIGINT ids on the shared metadata).
_TEST_DB_URL = os.environ.get("ALERTD_TEST_DATABASE_URL") or None

from app.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.main import create_app  # noqa: E402

# Reset settings cache so the test env vars take effect even if a prior
# test run loaded different values.
get_settings.cache_clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ── Pure-unit (no DB) ─────────────────────────────────────────────


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """In-process FastAPI client. No lifespan startup (so no DB
    init, no MQTT, no engine)."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ── DB-backed ─────────────────────────────────────────────────────


@pytest.fixture
async def db_engine():
    """Fresh in-memory SQLite engine + schema per test.

    Patches the module-level ``_engine`` and ``_session_factory`` so
    any caller of ``get_session_factory()`` sees this engine. Cleans
    up at teardown.
    """
    from app.db import session as session_module

    if _TEST_DB_URL:
        # Real MySQL (audit V03-V06): real BIGINT ids, real locking and the
        # MySQL-specific upsert paths. Fresh schema per test for isolation.
        engine = create_async_engine(_TEST_DB_URL, echo=False, pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    else:
        # StaticPool + a single shared in-memory database — without this,
        # each pooled connection gets its own private :memory: SQLite and
        # writes from one connection are invisible to the next request.
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

        # Enforce foreign keys in SQLite (off by default) so FK ordering bugs
        # — e.g. inserting a child before its parent — fail in tests the same
        # way they do on MySQL in production, instead of silently passing.
        from sqlalchemy import event

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_fk_on(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        # SQLite only auto-increments columns of the exact "INTEGER
        # PRIMARY KEY" affinity. Production MySQL uses BIGINT, but for
        # tests we coerce primary-key BIGINTs to INTEGER so explicit ids
        # aren't required for every insert. The change is on the
        # in-memory metadata for this test only — production schema is
        # untouched.
        from sqlalchemy import BigInteger, Integer

        for table in Base.metadata.tables.values():
            for col in table.columns:
                if col.primary_key and isinstance(col.type, BigInteger):
                    col.type = Integer()

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Match production (app/db/session.py): autoflush=False. With the
    # default autoflush=True, a lookup SELECT would implicitly flush
    # pending inserts and hide ordering/visibility bugs that bite on the
    # real engine (audit F01 test-fidelity gap).
    factory = async_sessionmaker(
        bind=engine, expire_on_commit=False, autoflush=False,
    )

    # Patch module globals so app.db.get_session{,_factory} returns
    # the test engine.
    prev_engine = session_module._engine
    prev_factory = session_module._session_factory
    session_module._engine = engine
    session_module._session_factory = factory
    try:
        yield engine
    finally:
        await engine.dispose()
        session_module._engine = prev_engine
        session_module._session_factory = prev_factory


@pytest.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    """Single-test ORM session. Auto-rollback at teardown so no row
    bleeds across tests."""
    from app.db import session as session_module

    async with session_module._session_factory() as s:
        try:
            yield s
        finally:
            await s.rollback()


@pytest.fixture
async def db_client(db_engine) -> AsyncIterator[AsyncClient]:
    """FastAPI test client backed by the in-memory SQLite engine.

    The DB layer is already patched by the ``db_engine`` fixture, so
    ``get_session`` (which both the request dependency and the API key
    resolver use) sees the test engine. Returns an httpx async client
    bound to the in-process app.
    """
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
async def admin_key(db_session) -> str:
    """Seed an admin API key into the test DB and return its plaintext.

    Must match alertd's auth model: 8-char prefix, bcrypt hash of full
    key, scopes including ``admin``."""
    import bcrypt

    from app.db.models import ApiKey

    plaintext = "alertd_test_admin_key_xxxxxxxx"  # ≥16 chars
    prefix = plaintext[:8]
    hashed = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=4)).decode()
    db_session.add(
        ApiKey(
            id=1,
            name="test_admin",
            key_hash=hashed,
            key_prefix=prefix,
            scopes=["admin"],
            enabled=True,
        )
    )
    await db_session.commit()
    return plaintext


# ── Object factories ──────────────────────────────────────────────


# SQLite doesn't auto-increment BIGINT primary keys — only the
# exact "INTEGER PRIMARY KEY" affinity. The factories below supply
# explicit ids drawn from a per-test counter so callers don't have
# to think about it. Production MySQL keeps using AUTO_INCREMENT.


@pytest.fixture
def make_template():
    """Build a Template ORM instance with sensible defaults; pass
    overrides via kwargs."""
    from app.db.models import Severity, Template

    counter = {"n": 100}

    def _factory(**overrides):
        counter["n"] += 1
        defaults = dict(
            id=overrides.pop("id", counter["n"]),
            type=overrides.pop("type", f"test_type_{counter['n']}"),
            severity=Severity.warning,
            icon="⚠️",
            title_template="{name} fired",
            message_template="value={value}",
            min_repeat_min=0,
            enabled=True,
        )
        defaults.update(overrides)
        return Template(**defaults)

    return _factory


@pytest.fixture
def make_rule():
    """Build a Rule ORM instance."""
    from app.db.models import Rule

    counter = {"n": 200}

    def _factory(**overrides):
        counter["n"] += 1
        defaults = dict(
            id=overrides.pop("id", counter["n"]),
            name=f"test_rule_{counter['n']}",
            template_type="test_type",
            condition_expr="True",
            persist_n=1,
            eval_interval_sec=30,
            vars_extract=[],
            enabled=True,
        )
        defaults.update(overrides)
        return Rule(**defaults)

    return _factory


@pytest.fixture
def make_channel():
    """Build a Channel ORM instance."""
    from app.db.models import Channel, ChannelKind

    counter = {"n": 300}

    def _factory(**overrides):
        counter["n"] += 1
        defaults = dict(
            id=overrides.pop("id", counter["n"]),
            name=overrides.pop("name", f"test_channel_{counter['n']}"),
            kind=ChannelKind.ui,
            config={},
            enabled=True,
        )
        defaults.update(overrides)
        return Channel(**defaults)

    return _factory


@pytest.fixture(autouse=True)
def _fresh_key_failure_budget():
    """Wrong-key counts are per client address and every test client has the
    same one: without this a test's 401s would turn a later test's into 429s.
    Key rate allowances are by key id, and ids repeat in every test database."""
    from app.auth import reset_key_failures, reset_key_rates

    reset_key_failures()
    reset_key_rates()
    yield
    reset_key_failures()
    reset_key_rates()


@pytest.fixture(autouse=True)
def _fresh_activity_log():
    """Each test starts with an empty activity-log queue and rule cache, so rows
    recorded by one test's requests never land in the next test's database."""
    from app.core.activity import reset_activity_writer_for_tests
    from app.core.activity_rules import reset_rule_cache_for_tests

    reset_activity_writer_for_tests()
    reset_rule_cache_for_tests()
    yield
    reset_activity_writer_for_tests()
    reset_rule_cache_for_tests()
