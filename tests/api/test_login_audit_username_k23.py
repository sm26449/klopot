"""A failed sign-in never puts what was typed as a username into the audit log (review K23).

``auth.login_failed`` / ``auth.login_blocked`` stored the typed username as
``resource_id``, and ``GET /v1/audit`` is ``read`` scope. A password typed into
the username field — a common slip — became readable by any read key. The
audit now names an existing account; anything else is recorded as
``unknown:<short digest>`` (still lets attempts on one name be correlated).
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.passwords import hash_password
from app.db.models import AdminUser, AuditLog
from tests._db import fresh

MISTYPED_NAME = "Correct-Horse-Battery-K23"


async def test_the_typed_name_of_no_account_is_not_stored(db_client, db_session, admin_key):
    db_session.add(AdminUser(id=1, username="admin", password_hash=hash_password("the-real-password-1"),
                             role="admin", is_active=True, must_change_password=False))
    await db_session.commit()
    await db_client.post("/v1/auth/login", json={"username": MISTYPED_NAME, "password": "x" * 12})
    await db_client.post("/v1/auth/login", json={"username": "admin", "password": "wrong-password-1"})

    await fresh(db_session)
    rows = (await db_session.execute(select(AuditLog).where(AuditLog.action == "auth.login_failed"))).scalars().all()
    ids = sorted(r.resource_id for r in rows)
    assert ids[0] == "admin"
    assert ids[1].startswith("unknown:")
    listed = await db_client.get("/v1/audit", headers={"X-API-Key": admin_key})
    assert MISTYPED_NAME not in listed.text
