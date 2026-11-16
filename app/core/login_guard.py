"""Login lockout — sliding window over ``login_attempts``.

Policy (``Settings.login_*``), all within the last ``login_lockout_min``
minutes and, for a username, since its last successful login:

- ``login_max_failures`` failures for a username **from one address** lock
  that username there;
- ``login_max_failures_per_user`` failures for a username from **any**
  address lock it everywhere — a ceiling for a distributed guesser, set
  well above the first so one remote address cannot lock the admin out
  (public-exposure review F8; until 1.2 the first limit was global);
- ``login_max_failures_per_ip`` failures from an address lock it for every
  username.

An address is its unit (``utils/failure_budget.address_unit``): IPv4 as is,
IPv6 by its /64 — a client gets a whole /64, so one budget per /128 would be
one per request. ``login_attempts.ip`` stores that unit.

A lock lifts by itself when the oldest counted failure ages out of the
window — there is no separate "lockout state" to forget or to unlock, which
also means a service restart cannot clear it.

The decision logic is pure (``decide``); the DB access lives in the two
small async helpers so the API handler stays thin.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import false, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import LoginAttempt
from ..utils.failure_budget import address_unit
from ..utils.time import utc_now


@dataclass(frozen=True)
class LockDecision:
    locked: bool
    retry_after_sec: int = 0
    reason: str | None = None  # "username" (from this address) | "username_everywhere" | "ip"


@dataclass(frozen=True)
class Limits:
    window_min: int
    per_user_and_ip: int
    per_user: int
    per_ip: int


def decide(
    *,
    now: datetime,
    limits: Limits,
    user_failures: list[tuple[datetime, str | None]],
    ip_failures: list[datetime],
    ip: str | None,
) -> LockDecision:
    """Pure decision. ``user_failures`` are the username's failed attempts
    (time, address unit) already restricted to the window and to after its
    last success; ``ip_failures`` the address's, restricted to the window.
    Oldest-first order is not required."""
    window = timedelta(minutes=limits.window_min)

    def _retry(ts_list: list[datetime], limit: int) -> int:
        # The lock lifts when the (limit)-th most recent failure leaves
        # the window.
        ordered = sorted(ts_list, reverse=True)
        pivot = ordered[limit - 1]
        return max(1, int((pivot + window - now).total_seconds()))

    here = [ts for ts, unit in user_failures if ip is not None and unit == ip]
    everywhere = [ts for ts, _unit in user_failures]
    if len(here) >= limits.per_user_and_ip:
        return LockDecision(True, _retry(here, limits.per_user_and_ip), "username")
    if len(everywhere) >= limits.per_user:
        return LockDecision(True, _retry(everywhere, limits.per_user), "username_everywhere")
    if len(ip_failures) >= limits.per_ip:
        return LockDecision(True, _retry(ip_failures, limits.per_ip), "ip")
    return LockDecision(False)


async def check(session: AsyncSession, *, username: str, ip: str | None, limits: Limits) -> LockDecision:
    """Load the relevant failures and decide. ``ip`` is the client address
    as seen (``auth.client_address``); it is compared by its unit."""
    unit = address_unit(ip) if ip else None
    now = utc_now()
    since = now - timedelta(minutes=limits.window_min)

    last_ok = (
        await session.execute(
            select(func.max(LoginAttempt.ts)).where(
                LoginAttempt.username == username, LoginAttempt.success == true()
            )
        )
    ).scalar_one_or_none()
    user_since = max(since, last_ok) if last_ok else since
    user_failures = [
        (ts, row_ip) for ts, row_ip in (
            await session.execute(
                select(LoginAttempt.ts, LoginAttempt.ip).where(
                    LoginAttempt.username == username,
                    LoginAttempt.success == false(),
                    LoginAttempt.ts > user_since,
                )
            )
        ).all()
    ]

    ip_failures: list[datetime] = []
    if unit:
        ip_failures = list(
            (
                await session.execute(
                    select(LoginAttempt.ts).where(
                        LoginAttempt.ip == unit,
                        LoginAttempt.success == false(),
                        LoginAttempt.ts > since,
                    )
                )
            ).scalars()
        )

    return decide(now=now, limits=limits, user_failures=user_failures, ip_failures=ip_failures, ip=unit)


async def record(
    session: AsyncSession, *, username: str | None, ip: str | None, success: bool
) -> None:
    """Append one attempt row, the address stored as its unit. Caller commits."""
    session.add(LoginAttempt(ts=utc_now(), username=username, ip=address_unit(ip) if ip else None,
                             success=success))


__all__ = ["Limits", "LockDecision", "check", "decide", "record"]
