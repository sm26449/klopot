"""Wrong API keys are bounded (audit P07).

A wrong key sharing a real key's prefix costs a bcrypt per key in the bucket.
Unbounded, an unauthenticated client stalled the service: the hashing pool
filled up and every waiting request held a database connection.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import auth
from app.db.models import ApiKey

pytestmark = pytest.mark.anyio


def _h(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def _wrong(i: int) -> str:
    return f"alertd_wrong_key_number_{i:04d}_xxxxxxxx"


async def test_an_address_gets_five_wrong_keys_a_minute(db_client, admin_key):
    assert (await db_client.get("/v1/channels", headers=_h(admin_key))).status_code == 200   # now cached
    for i in range(auth._KEY_BUDGET.max_failures):
        assert (await db_client.get("/v1/channels", headers=_h(_wrong(i)))).status_code == 401
    r = await db_client.get("/v1/channels", headers=_h(_wrong(99)))
    assert r.status_code == 429
    assert r.headers["retry-after"] == "60"
    # A key that is already verified keeps working from the same address.
    assert (await db_client.get("/v1/channels", headers=_h(admin_key))).status_code == 200


async def test_a_spent_budget_costs_no_hash(db_client, monkeypatch):
    for i in range(auth._KEY_BUDGET.max_failures):
        await db_client.get("/v1/channels", headers=_h(_wrong(i)))
    hashed: list[bytes] = []

    async def spy(raw: bytes, _hashed: bytes) -> bool:
        hashed.append(raw)
        return False

    monkeypatch.setattr(auth, "_checkpw_async", spy)
    assert (await db_client.get("/v1/channels", headers=_h(_wrong(100)))).status_code == 429
    assert hashed == []


async def test_the_budget_expires_and_is_per_address(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(auth._KEY_BUDGET, "_clock", lambda: clock[0])
    for _ in range(auth._KEY_BUDGET.max_failures):
        auth._KEY_BUDGET.note("203.0.113.7")
    assert auth._KEY_BUDGET.spent("203.0.113.7")
    assert not auth._KEY_BUDGET.spent("203.0.113.8")
    assert not auth._KEY_BUDGET.spent(None)
    clock[0] += auth._KEY_BUDGET.window_sec + 1
    assert not auth._KEY_BUDGET.spent("203.0.113.7")
    assert "203.0.113.7" not in auth._KEY_BUDGET


async def test_the_failure_table_is_bounded(monkeypatch):
    monkeypatch.setattr(auth._KEY_BUDGET, "max_addresses", 50)
    for i in range(500):
        auth._KEY_BUDGET.note(f"198.51.100.{i}")
    assert len(auth._KEY_BUDGET) <= 50


async def _seed_key(db_session, raw: str) -> None:
    db_session.add(ApiKey(name="bucket", key_prefix=raw[:8], key_hash=auth.hash_key(raw), scopes=["read"], enabled=True))
    await db_session.commit()


async def test_no_database_transaction_is_open_while_hashing(db_session, monkeypatch):
    real = "alertd_real_key_for_the_bucket_0000001"
    await _seed_key(db_session, real)
    seen: list[bool] = []

    async def spy(raw: bytes, _hashed: bytes) -> bool:
        seen.append(db_session.in_transaction())
        return False

    monkeypatch.setattr(auth, "_checkpw_async", spy)
    with pytest.raises(HTTPException) as e:
        await auth._resolve_key("alertd_rxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", db_session, "203.0.113.9")
    assert e.value.status_code == 401
    assert seen == [False], "the connection must be back in the pool before the hash"


async def test_a_full_hashing_queue_answers_503_at_once(db_session, monkeypatch):
    real = "alertd_real_key_for_the_bucket_0000002"
    await _seed_key(db_session, real)
    monkeypatch.setattr(auth, "_key_verifies_pending", 10_000)
    with pytest.raises(HTTPException) as e:
        await auth._resolve_key("alertd_rxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", db_session, "203.0.113.10")
    assert e.value.status_code == 503
    assert e.value.headers == {"Retry-After": "1"}
    # The right key is not counted as a failure and still verifies once there is room.
    monkeypatch.setattr(auth, "_key_verifies_pending", 0)
    actor = await auth._resolve_key(real, db_session, "203.0.113.10")
    assert actor.name == "bucket"
    assert auth._key_verifies_pending == 0


# ── Digest lookup (migration 0034) ────────────────────────────────────────────


def test_only_generated_keys_get_a_digest():
    generated = auth.generate_key_plaintext()
    assert len(auth.key_digest(generated)) == 64
    assert auth.key_digest(generated) != auth.key_digest(auth.generate_key_plaintext())
    # Chosen by the operator: maybe weak, so never stored as a fast hash.
    assert auth.key_digest("alertd_bootstrap") is None
    assert auth.key_digest("alertd_" + "a" * 42) is None
    assert auth.key_digest("other_" + "a" * 43) is None


async def test_a_new_key_is_found_without_bcrypt(db_client, admin_key, db_session, monkeypatch):
    # The bucket is the first 8 characters ("alertd_" + one). If the new key
    # shared the fixture admin key's bucket — a key without a digest — a wrong
    # key there would rightly be bcrypt-checked against it (1 run in 64).
    for n in range(10):
        created = (await db_client.post("/v1/api_keys", headers=_h(admin_key),
                                        json={"name": f"fast{n}", "scopes": ["read"]})).json()
        if created["key"][:8] != admin_key[:8]:
            break
    row = (await db_session.execute(select(ApiKey).where(ApiKey.id == created["id"]))).scalar_one()
    assert row.key_digest == auth.key_digest(created["key"])

    async def no_hashing(*_a: object) -> bool:
        raise AssertionError("bcrypt must not run for a key that has a digest")

    monkeypatch.setattr(auth, "_checkpw_async", no_hashing)
    assert (await db_client.get("/v1/channels", headers=_h(created["key"]))).status_code == 200
    # A wrong key of the generated shape: one indexed read, no hash either
    # (the bucket holds no key without a digest that it could be).
    wrong = created["key"][:8] + auth.generate_key_plaintext()[8:]
    assert (await db_client.get("/v1/channels", headers=_h(wrong))).status_code == 401


async def test_a_right_key_gets_in_from_an_address_that_spent_its_budget(db_client, admin_key):
    created = (await db_client.post("/v1/api_keys", headers=_h(admin_key), json={"name": "fast2", "scopes": ["read"]})).json()
    for i in range(auth._KEY_BUDGET.max_failures + 2):
        await db_client.get("/v1/channels", headers=_h(_wrong(i)))
    assert (await db_client.get("/v1/channels", headers=_h(_wrong(50)))).status_code == 429
    assert (await db_client.get("/v1/channels", headers=_h(created["key"]))).status_code == 200


async def test_an_older_key_gets_its_digest_on_first_use(db_session):
    """Issued before 0034: bcrypt once, then the digest path."""
    raw = auth.generate_key_plaintext()
    db_session.add(ApiKey(name="older", key_prefix=raw[:8], key_hash=auth.hash_key(raw), scopes=["read"], enabled=True))
    await db_session.commit()
    assert (await auth._resolve_key(raw, db_session, "203.0.113.20")).name == "older"
    await db_session.commit()
    row = (await db_session.execute(select(ApiKey).where(ApiKey.name == "older"))).scalar_one()
    await db_session.refresh(row)
    assert row.key_digest == auth.key_digest(raw)


async def test_an_operator_chosen_key_keeps_bcrypt_only(db_session):
    raw = "alertd_chosen_by_the_operator"
    await _seed_key(db_session, raw)
    assert (await auth._resolve_key(raw, db_session, "203.0.113.21")).name == "bucket"
    await db_session.commit()
    row = (await db_session.execute(select(ApiKey).where(ApiKey.name == "bucket"))).scalar_one()
    await db_session.refresh(row)
    assert row.key_digest is None


async def test_a_disabled_or_expired_key_with_a_digest_is_refused(db_client, admin_key, db_session):
    h = _h(admin_key)
    created = (await db_client.post("/v1/api_keys", headers=h, json={"name": "gone", "scopes": ["read"]})).json()
    assert (await db_client.patch(f"/v1/api_keys/{created['id']}", headers=h, json={"enabled": False})).status_code == 200
    assert (await db_client.get("/v1/channels", headers=_h(created["key"]))).status_code == 401
    expired = (await db_client.post("/v1/api_keys", headers=h, json={
        "name": "late", "scopes": ["read"], "expires_at": "2020-01-01T00:00:00Z"})).json()
    r = await db_client.get("/v1/channels", headers=_h(expired["key"]))
    assert r.status_code == 401
    assert r.json()["detail"] == "API key expired"


async def test_the_digest_never_reaches_a_response_or_the_audit_log(db_client, admin_key):
    h = _h(admin_key)
    created = (await db_client.post("/v1/api_keys", headers=h, json={"name": "quiet", "scopes": ["read"]})).json()
    digest = auth.key_digest(created["key"])
    assert "key_digest" not in created
    listing = (await db_client.get("/v1/api_keys", headers=h)).text
    assert digest not in listing
    assert "key_digest" not in listing
    # The audit row names the column, masked like key_hash.
    audit = (await db_client.get("/v1/audit", headers=h)).text
    assert digest not in audit
    assert '"key_digest":"<redacted>"' in audit
