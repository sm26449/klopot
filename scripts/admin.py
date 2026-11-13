"""Break-glass administration of the admin-UI account (runs in the container).

    docker compose exec alertd python -m scripts.admin reset-password
    docker compose exec alertd python -m scripts.admin unlock
    docker compose exec alertd python -m scripts.admin list-sessions
    docker compose exec alertd python -m scripts.admin revoke-sessions

Every command needs shell access to the container (= host root), which
is the trust boundary: there is deliberately no API equivalent for
resetting a password without knowing the current one.

``reset-password`` prints a temporary password ONCE, sets
``must_change_password=1`` and revokes every session of the account;
the next login forces a change. All actions land in ``audit_log`` with
``actor_kind=system``.

Note: the running service caches session lookups for 30 s; a revoke
from here takes effect within that window (restart to make it instant).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import delete, select

from app.audit import record_change
from app.auth import Actor
from app.core.passwords import generate_temp_password, hash_password
from app.db import dispose_engine, init_engine
from app.db.models import AdminSession, AdminUser, LoginAttempt
from app.utils.time import utc_now

logger = logging.getLogger("scripts.admin")

_SYSTEM = Actor(kind="system", id=None, name="scripts.admin", scopes=frozenset())


def _factory():
    init_engine()
    from app.db.session import _session_factory as factory

    if factory is None:
        raise RuntimeError("Session factory not initialized")
    return factory


async def _get_user(session, username: str) -> AdminUser:
    user = (
        await session.execute(select(AdminUser).where(AdminUser.username == username))
    ).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"no admin user named {username!r}")
    return user


async def _revoke_all(session, user_id: int) -> int:
    rows = (
        await session.execute(
            select(AdminSession).where(
                AdminSession.user_id == user_id, AdminSession.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    now = utc_now()
    for r in rows:
        r.revoked_at = now
    return len(rows)


async def cmd_reset_password(username: str) -> None:
    async with _factory()() as session:
        user = await _get_user(session, username)
        temp = generate_temp_password()
        user.password_hash = hash_password(temp)
        user.must_change_password = True
        user.is_active = True
        user.password_changed_at = utc_now()
        revoked = await _revoke_all(session, user.id)
        await record_change(
            session, _SYSTEM, "auth.password_reset_cli",
            resource_kind="admin_user", resource_id=username,
            after={"sessions_revoked": revoked, "must_change_password": True},
        )
        await session.commit()
    print(f"Temporary password for {username!r} (shown once, change it at first login):")
    print(f"  {temp}")
    print(f"Revoked {revoked} active session(s).")


async def cmd_unlock(username: str) -> None:
    async with _factory()() as session:
        await _get_user(session, username)
        r = await session.execute(
            delete(LoginAttempt).where(
                LoginAttempt.username == username, LoginAttempt.success.is_(False)
            )
        )
        await record_change(
            session, _SYSTEM, "auth.unlock_cli",
            resource_kind="admin_user", resource_id=username,
            after={"failed_attempts_cleared": r.rowcount},
        )
        await session.commit()
    print(f"Cleared {r.rowcount} failed attempt(s) for {username!r}; lockout lifted.")


async def cmd_list_sessions(username: str) -> None:
    async with _factory()() as session:
        user = await _get_user(session, username)
        rows = (
            await session.execute(
                select(AdminSession)
                .where(AdminSession.user_id == user.id)
                .order_by(AdminSession.last_seen_at.desc())
                .limit(50)
            )
        ).scalars().all()
    now = utc_now()
    print(f"{'id':>5}  {'state':8}  {'last_seen (UTC)':19}  {'expires (UTC)':19}  ip  user_agent")
    for r in rows:
        state = "revoked" if r.revoked_at else ("expired" if r.expires_at <= now else "active")
        print(
            f"{r.id:>5}  {state:8}  {r.last_seen_at:%Y-%m-%d %H:%M:%S}  "
            f"{r.expires_at:%Y-%m-%d %H:%M:%S}  {r.ip or '-'}  {(r.user_agent or '-')[:60]}"
        )


async def cmd_revoke_sessions(username: str) -> None:
    async with _factory()() as session:
        user = await _get_user(session, username)
        revoked = await _revoke_all(session, user.id)
        await record_change(
            session, _SYSTEM, "auth.sessions_revoked_cli",
            resource_kind="admin_user", resource_id=username,
            after={"sessions_revoked": revoked},
        )
        await session.commit()
    print(f"Revoked {revoked} active session(s) for {username!r}.")


async def _main(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="scripts.admin", description=__doc__.split("\n\n")[0])
    p.add_argument("--username", default="admin")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reset-password", help="set a temporary password, force change, revoke sessions")
    sub.add_parser("unlock", help="clear failed login attempts (lifts lockout)")
    sub.add_parser("list-sessions", help="show the account's sessions")
    sub.add_parser("revoke-sessions", help="revoke every active session")
    args = p.parse_args(argv)

    logging.basicConfig(level="WARNING")
    try:
        if args.cmd == "reset-password":
            await cmd_reset_password(args.username)
        elif args.cmd == "unlock":
            await cmd_unlock(args.username)
        elif args.cmd == "list-sessions":
            await cmd_list_sessions(args.username)
        elif args.cmd == "revoke-sessions":
            await cmd_revoke_sessions(args.username)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
