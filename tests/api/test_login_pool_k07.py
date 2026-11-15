"""A sign-in never holds a database connection while it waits for argon2 (review K07).

``/v1/auth/login`` is anonymous. It read the lockout state and the user, then
waited for one of ``hash_max_concurrency`` argon2 slots (~100 ms each) with the
read transaction — and its pooled connection — still open, and the wait queue
had no ceiling. Fifteen concurrent wrong logins held the whole pool; a steady
flood kept the engine, the delivery worker and every request waiting for a
connection. Now the transaction ends before hashing, and past 16 waiting
sign-ins the answer is 503.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy.orm.session import _sessions

from app.core import crypto_pool, passwords
from app.core.passwords import hash_password
from app.db.models import AdminUser

pytestmark = pytest.mark.anyio

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
async def admin_user(db_session) -> AdminUser:
    user = AdminUser(id=1, username="admin", password_hash=hash_password(PASSWORD),
                     role="admin", is_active=True, must_change_password=False)
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture(autouse=True)
def _fresh_pool():
    crypto_pool.reset_for_tests()
    yield
    crypto_pool.reset_for_tests()


def _slow_verify(seen: list[int], probe):
    real = passwords.verify_password

    def verify(stored_hash, plaintext):
        # Measure after a pause: by then every concurrent sign-in has done its
        # reads and is hashing or waiting for a slot.
        time.sleep(0.3)
        seen.append(probe())
        return real(stored_hash, plaintext)
    return verify


async def test_no_transaction_is_open_while_the_password_is_checked(db_client, admin_user, monkeypatch):
    def open_transactions() -> int:
        return sum(1 for s in list(_sessions.values()) if s.in_transaction())

    seen: list[int] = []
    monkeypatch.setattr(passwords, "verify_password", _slow_verify(seen, open_transactions))
    r = await db_client.post("/v1/auth/login", json={"username": "admin", "password": "wrong-password-1"})
    assert r.status_code == 401
    assert seen == [0], "the login's read transaction was still open during the hash"
    ok = await db_client.post("/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert ok.status_code == 200, ok.text[:200]


async def test_sign_ins_beyond_the_queue_get_503(db_client, admin_user, monkeypatch):
    from app.api.v1 import auth as auth_route

    monkeypatch.setattr(auth_route, "_LOGIN_VERIFY_QUEUE_MAX", 0)
    seen: list[int] = []
    monkeypatch.setattr(passwords, "verify_password", _slow_verify(seen, lambda: 0))
    limit = crypto_pool.get_settings().hash_max_concurrency
    attempts = [db_client.post("/v1/auth/login", json={"username": f"u{i}", "password": "x" * 12})
                for i in range(limit + 3)]
    codes = sorted(r.status_code for r in await asyncio.gather(*attempts))
    assert codes.count(503) == 3, codes
    assert codes.count(401) == limit, codes


@pytest.mark.mysql
async def test_concurrent_logins_hold_no_pooled_connection(db_client, admin_user, monkeypatch):
    """Twice as many sign-ins as hashing slots: while the first wave hashes and
    the second waits for a slot, the pool has nothing checked out.

    The first wave measures together (a barrier) and nobody leaves the hash
    before every one of them has measured: a sign-in that finished hashing
    writes its failure and briefly takes a connection, which a measurement
    of the global pool must not see (the earlier, unsynchronised version
    failed in CI 1 time in ~30 with one sample of 1)."""
    import itertools
    import threading

    from app.db import session as session_module

    pool = session_module._engine.pool
    slots = crypto_pool.get_settings().hash_max_concurrency
    real = passwords.verify_password
    seen: list[int] = []
    first_wave = itertools.count()
    lock = threading.Lock()
    barrier = threading.Barrier(slots, timeout=20)

    def verify(stored_hash, plaintext):
        with lock:
            measuring = next(first_wave) < slots
        if measuring:
            barrier.wait()           # the whole first wave is hashing; the rest wait for a slot
            time.sleep(0.3)          # …and have finished their reads by now
            seen.append(pool.checkedout())
            barrier.wait()           # nobody goes on to write its failure before all measured
        return real(stored_hash, plaintext)

    monkeypatch.setattr(passwords, "verify_password", verify)
    attempts = [db_client.post("/v1/auth/login", json={"username": f"user{i}", "password": "x" * 12})
                for i in range(2 * slots)]
    codes = [r.status_code for r in await asyncio.gather(*attempts)]
    assert codes == [401] * (2 * slots)
    assert len(seen) == slots
    assert max(seen) == 0, f"connections checked out while hashing or waiting for a slot: {seen}"
