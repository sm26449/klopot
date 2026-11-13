"""Login lockout — sliding window over ``login_attempts``.

Policy (``Settings.login_*``): a username is locked when it has
``login_max_failures`` failed attempts in the last ``login_lockout_min``
minutes *since its last successful login*; a source IP is locked at
``login_max_failures_per_ip`` failures in the same window (any
username). A lock lifts by itself when the oldest counted failure ages
out of the window — there is no separate "lockout state" to forget or
to unlock, which also means a service restart cannot clear it.

The decision logic is pure (``decide``); the DB access lives in the
two small async helpers so the API handler stays thin.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import LoginAttempt
from ..utils.time import utc_now


@dataclass(frozen=True)
class LockDecision:
    locked: bool
    retry_after_sec: int = 0
    reason: str | None = None  # "username" | "ip"


def decide(
    *,
    now: datetime,
    window_min: int,
    user_failures: list[datetime],
    ip_failures: list[datetime],
    max_user: int,
    max_ip: int,
) -> LockDecision:
    """Pure decision. ``*_failures`` are the timestamps of failed
    attempts already restricted to the window (and, for the user, to
    after the last success). Oldest-first order is not required."""
    window = timedelta(minutes=window_min)

    def _retry(ts_list: list[datetime], limit: int) -> int:
        # The lock lifts when the (limit)-th most recent failure leaves
        # the window.
        ordered = sorted(ts_list, reverse=True)
        pivot = ordered[limit - 1]
        return max(1, int((pivot + window - now).total_seconds()))

    if len(user_failures) >= max_user:
        return LockDecision(True, _retry(user_failures, max_user), "username")
    if len(ip_failures) >= max_ip:
        return LockDecision(True, _retry(ip_failures, max_ip), "ip")
    return LockDecision(False)


async def check(
    session: AsyncSession,
    *,
    username: str,
    ip: str | None,
    window_min: int,
    max_user: int,
    max_ip: int,
) -> LockDecision:
    """Load the relevant failures and decide."""
    now = utc_now()
    since = now - timedelta(minutes=window_min)

    last_ok = (
        await session.execute(
            select(func.max(LoginAttempt.ts)).where(
                LoginAttempt.username == username, LoginAttempt.success.is_(True)
            )
        )
    ).scalar_one_or_none()
    user_since = max(since, last_ok) if last_ok else since
    user_failures = list(
        (
            await session.execute(
                select(LoginAttempt.ts).where(
                    LoginAttempt.username == username,
                    LoginAttempt.success.is_(False),
                    LoginAttempt.ts > user_since,
                )
            )
        ).scalars()
    )

    ip_failures: list[datetime] = []
    if ip:
        ip_failures = list(
            (
                await session.execute(
                    select(LoginAttempt.ts).where(
                        LoginAttempt.ip == ip,
                        LoginAttempt.success.is_(False),
                        LoginAttempt.ts > since,
                    )
                )
            ).scalars()
        )

    return decide(
        now=now,
        window_min=window_min,
        user_failures=user_failures,
        ip_failures=ip_failures,
        max_user=max_user,
        max_ip=max_ip,
    )


async def record(
    session: AsyncSession, *, username: str | None, ip: str | None, success: bool
) -> None:
    """Append one attempt row. Caller commits."""
    session.add(LoginAttempt(ts=utc_now(), username=username, ip=ip, success=success))


__all__ = ["LockDecision", "check", "decide", "record"]
