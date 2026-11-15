"""Pure-unit tests for ``app.core.passwords``."""
from __future__ import annotations

from app.core import passwords


def test_hash_and_verify_roundtrip():
    h = passwords.hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert passwords.verify_password(h, "correct horse battery staple")
    assert not passwords.verify_password(h, "correct horse battery stapl")


def test_verify_against_missing_or_garbage_hash_is_false():
    assert passwords.verify_password(None, "anything-at-all-here") is False
    assert passwords.verify_password("not-a-hash", "anything-at-all-here") is False


def test_hashes_are_salted():
    assert passwords.hash_password("same-password-twice") != passwords.hash_password(
        "same-password-twice"
    )


def test_needs_rehash_false_for_fresh_true_for_garbage():
    assert passwords.needs_rehash(passwords.hash_password("fresh-password-1234")) is False
    assert passwords.needs_rehash("$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$AAAA") is True
    assert passwords.needs_rehash("garbage") is True


def test_policy_length_bounds():
    assert passwords.validate_password_policy("short", username="admin")
    assert passwords.validate_password_policy("x" * 257, username="admin")
    assert passwords.validate_password_policy("exactly-12ch", username="admin") == []


def test_policy_username_and_current_and_whitespace():
    assert "must differ from the username" in passwords.validate_password_policy(
        "Administrator", username="administrator"
    )
    assert "must differ from the current password" in passwords.validate_password_policy(
        "same-password-here", username="admin", current_password="same-password-here"
    )
    assert passwords.validate_password_policy(" leading-space-pw", username="admin")


def test_temp_password_shape():
    p = passwords.generate_temp_password()
    assert len(p) == 20
    assert p.isalnum()
    assert passwords.validate_password_policy(p, username="admin") == []


# ── A13: async offloaded variants ─────────────────────────────────


async def test_hash_password_async_roundtrip():
    h = await passwords.hash_password_async("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert await passwords.verify_password_async(h, "correct horse battery staple")
    assert not await passwords.verify_password_async(h, "wrong-password-xx")


async def test_verify_password_async_missing_hash_is_false():
    assert await passwords.verify_password_async(None, "anything-at-all-here") is False
