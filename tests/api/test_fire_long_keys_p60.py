"""The longest valid episode key fits its column (audit P60).

``fire:<api key name>:<idempotency_key>`` reaches 198 characters;
``incidents.source_key`` is VARCHAR(191). MySQL refused the insert (HTTP
500); SQLite does not enforce lengths, hence the unit test on the helper.
"""
from __future__ import annotations

import bcrypt
import pytest
from sqlalchemy import select

from app.db.models import ApiKey, Incident, Severity, Template
from app.inputs import alertmanager as am
from app.utils.keys import SOURCE_KEY_MAX, bounded_key
from tests._db import fresh


def test_bounded_key_is_stable_distinct_and_fits():
    short = "fire:node-red:disk-sda"
    assert bounded_key(short) == short
    long_a = "fire:" + "n" * 64 + ":" + "k" * 128
    long_b = long_a[:-1] + "x"          # differs only in the last character
    assert len(long_a) == 198
    assert len(bounded_key(long_a)) == SOURCE_KEY_MAX
    assert bounded_key(long_a) == bounded_key(long_a)
    assert bounded_key(long_a) != bounded_key(long_b)
    assert bounded_key("x" * SOURCE_KEY_MAX) == "x" * SOURCE_KEY_MAX


def test_an_alertmanager_fingerprint_of_any_length_fits():
    alert = am.Alert(status="firing", labels={"alertname": "x"}, annotations={}, fingerprint="f" * 500,
                     starts_at=None, ends_at=None, generator_url=None)
    assert len(am.episode_key(7, alert)) == SOURCE_KEY_MAX


@pytest.mark.mysql
async def test_longest_valid_key_and_idempotency_key_open_and_close_an_episode(db_client, db_session):
    plaintext = "alertd_longname_key_xxxxxxxxxxxx"
    db_session.add(ApiKey(id=7, name="n" * 64, key_prefix=plaintext[:8], scopes=["fire"], enabled=True,
                          key_hash=bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=4)).decode()))
    db_session.add(Template(type="disk_full", severity=Severity.critical, title_template="Disk full", min_repeat_min=0))
    await db_session.commit()
    body = {"type": "disk_full", "context": {}, "idempotency_key": "k" * 128}
    h = {"X-API-Key": plaintext}
    opened = await db_client.post("/v1/fire", headers=h, json=body)
    assert opened.status_code == 202, opened.text[:200]
    again = await db_client.post("/v1/fire", headers=h, json=body)
    assert again.status_code == 202, again.text[:200]
    await fresh(db_session)
    episodes = (await db_session.execute(select(Incident))).scalars().all()
    assert len(episodes) == 1, "the second fire found the episode again under the bounded key"
    assert len(episodes[0].source_key) == SOURCE_KEY_MAX
    assert episodes[0].active_source_key == episodes[0].source_key
    closed = await db_client.post("/v1/fire", headers=h, json={**body, "status": "resolved"})
    assert closed.status_code == 202, closed.text[:200]
    await fresh(db_session)
    episode = (await db_session.execute(select(Incident))).scalar_one()
    assert episode.active_source_key is None      # resolved: the key is free again
