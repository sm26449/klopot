"""Episode keys are case-sensitive on MySQL too (review K01).

``incidents.source_key`` / ``active_source_key`` used the server collation
``utf8mb4_unicode_ci``, so ``DiskFull`` and ``diskfull`` were one episode: the
second firing answered ``repeat`` and sent nothing, and a resolution of one key
closed the other. Clients treat ``idempotency_key`` as case-sensitive, and
SQLite always compared it that way — hence the DDL test, which the SQLite run
also checks.
"""
from __future__ import annotations

import bcrypt
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.db.models import ApiKey, Incident, Severity, Template
from tests._db import fresh

pytestmark = pytest.mark.anyio


def test_episode_key_columns_compare_bytes_on_mysql():
    ddl = str(CreateTable(Incident.__table__).compile(dialect=mysql.dialect()))
    for column in ("source_key", "active_source_key"):
        line = next(x for x in ddl.splitlines() if x.strip().startswith(column + " "))
        assert "utf8mb4_bin" in line, line


@pytest.mark.mysql
async def test_keys_that_differ_only_in_case_are_two_episodes(db_client, db_session):
    plaintext = "alertd_casekey_xxxxxxxxxxxxxxxx"
    db_session.add(ApiKey(id=9, name="producer", key_prefix=plaintext[:8], scopes=["fire"], enabled=True,
                          key_hash=bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=4)).decode()))
    db_session.add(Template(type="disk_full", severity=Severity.critical, title_template="Disk full", min_repeat_min=0))
    await db_session.commit()
    h = {"X-API-Key": plaintext}

    for key in ("DiskFull", "diskfull"):
        r = await db_client.post("/v1/fire", headers=h, json={"type": "disk_full", "context": {}, "idempotency_key": key})
        assert r.status_code == 202, r.text[:200]
    await fresh(db_session)
    episodes = (await db_session.execute(select(Incident).order_by(Incident.opened_at))).scalars().all()
    assert sorted(e.rule_name for e in episodes) == ["DiskFull", "diskfull"]

    r = await db_client.post("/v1/fire", headers=h, json={
        "type": "disk_full", "context": {}, "idempotency_key": "diskfull", "status": "resolved"})
    assert r.status_code == 202, r.text[:200]
    await fresh(db_session)
    still_open = (await db_session.execute(
        select(Incident.rule_name).where(Incident.active_source_key.is_not(None)))).scalars().all()
    assert still_open == ["DiskFull"], "resolving one key must not close the other"
