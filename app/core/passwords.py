"""Password hashing + policy for ``admin_users`` (pure, no I/O).

argon2id via ``argon2-cffi`` with the library defaults (time_cost=3,
memory_cost=64 MiB, parallelism=4, 32-byte hash, 16-byte salt) — the
OWASP first-choice KDF for low-entropy secrets. API keys keep bcrypt
(``app/auth.py``): they are 256-bit random strings and need speed, not
memory hardness.

Policy (decision D4, NIST SP 800-63B): length only — no composition
rules, no forced rotation. Minimum 12, maximum 256 characters, must
differ from the username and from the current password.
"""
from __future__ import annotations

import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

MIN_LENGTH = 12
MAX_LENGTH = 256

_hasher = PasswordHasher()

# A real argon2id hash of a random throwaway string. ``verify_password``
# runs against it when the username does not exist so the response time
# does not reveal which usernames are valid.
DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(24))


def hash_password(plaintext: str) -> str:
    """Return an argon2id PHC string (``$argon2id$v=19$m=...``)."""
    return _hasher.hash(plaintext)


async def hash_password_async(plaintext: str) -> str:
    """``hash_password`` offloaded to the bounded crypto pool (audit A13)
    so argon2 doesn't block the event loop."""
    from .crypto_pool import run_in_pool
    return await run_in_pool(hash_password, plaintext)


async def verify_password_async(
    stored_hash: str | None, plaintext: str, *, queue_max: int | None = None,
) -> bool:
    """``verify_password`` offloaded to the bounded crypto pool (audit A13).
    ``queue_max``: see :func:`crypto_pool.run_in_pool`."""
    from .crypto_pool import run_in_pool
    return await run_in_pool(verify_password, stored_hash, plaintext, queue_max=queue_max)


def verify_password(stored_hash: str | None, plaintext: str) -> bool:
    """Constant-shape verification: a missing/invalid hash still costs
    one argon2 computation (against ``DUMMY_HASH``) and returns False."""
    target = stored_hash or DUMMY_HASH
    try:
        return _hasher.verify(target, plaintext)
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        # Corrupted row — burn the same time, then reject.
        try:
            _hasher.verify(DUMMY_HASH, plaintext)
        except VerifyMismatchError:
            pass
        return False


def needs_rehash(stored_hash: str) -> bool:
    """True when the stored hash uses weaker parameters than current."""
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def validate_password_policy(
    new_password: str,
    *,
    username: str,
    current_password: str | None = None,
) -> list[str]:
    """Return the list of policy violations (empty = acceptable)."""
    problems: list[str] = []
    if len(new_password) < MIN_LENGTH:
        problems.append(f"must be at least {MIN_LENGTH} characters")
    if len(new_password) > MAX_LENGTH:
        problems.append(f"must be at most {MAX_LENGTH} characters")
    if new_password.strip() != new_password:
        problems.append("must not start or end with whitespace")
    if username and new_password.lower() == username.lower():
        problems.append("must differ from the username")
    if current_password is not None and new_password == current_password:
        problems.append("must differ from the current password")
    return problems


_TEMP_ALPHABET = string.ascii_letters + string.digits


def generate_temp_password(length: int = 20) -> str:
    """Random temporary password for the break-glass CLI reset.

    Letters + digits only so it survives copy/paste from a terminal."""
    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))


__all__ = [
    "DUMMY_HASH",
    "MAX_LENGTH",
    "MIN_LENGTH",
    "generate_temp_password",
    "hash_password",
    "hash_password_async",
    "needs_rehash",
    "validate_password_policy",
    "verify_password",
    "verify_password_async",
]
