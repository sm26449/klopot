"""Request-log rules: what the activity log keeps for a request (first match wins).

Rules live in ``activity_rules`` and are edited in the admin UI (Activity →
Rules). They are cached in memory and reloaded after every change (and every
``_TTL_SEC`` as a safety net). An ``ignore`` rule stores nothing but counts
the request (``hits``, ``last_hit_at``, ``last_ip``), so the operator still
sees that such requests arrive.
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..utils.time import utc_now

logger = logging.getLogger(__name__)

_TTL_SEC = 60.0
BODY_MODES = ("auto", "never", "errors", "always")
ACTIONS = ("keep", "ignore")
STATUS_CLASSES = ("1xx", "2xx", "3xx", "4xx", "5xx")


@dataclass(frozen=True)
class Rule:
    id: int
    name: str
    method: str | None
    path: str
    status: str | None
    actor: str | None
    ip: str | None
    action: str
    keep_days: int | None
    request_body: str
    response_body: str

    def matches(self, *, method: str, path: str, status: int, actor: str | None, ip: str | None) -> bool:
        if self.method and self.method.upper() != method.upper():
            return False
        if not fnmatch.fnmatchcase(path, self.path or "*"):
            return False
        if self.status:
            s = self.status.lower()
            if s in STATUS_CLASSES:
                if str(status)[0] != s[0]:
                    return False
            elif s != str(status):
                return False
        if self.actor and not fnmatch.fnmatchcase(actor or "", self.actor):
            return False
        return not (self.ip and not fnmatch.fnmatchcase(ip or "", self.ip))


class RuleCache:
    def __init__(self) -> None:
        self._rules: list[Rule] = []
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()
        # rule id → [count, last_at, last_ip] not yet written to the table.
        self._hits: dict[int, list[Any]] = {}

    def invalidate(self) -> None:
        self._loaded_at = 0.0

    async def rules(self) -> list[Rule]:
        if time.monotonic() - self._loaded_at < _TTL_SEC:
            return self._rules
        async with self._lock:
            if time.monotonic() - self._loaded_at < _TTL_SEC:
                return self._rules
            try:
                from sqlalchemy import select

                from ..db.models import ActivityRule
                from ..db.session import get_session_factory

                async with get_session_factory()() as s:
                    rows = (await s.execute(select(ActivityRule).where(ActivityRule.enabled.is_(True))
                                            .order_by(ActivityRule.position, ActivityRule.id))).scalars().all()
                self._rules = [Rule(r.id, r.name, r.match_method, r.match_path, r.match_status, r.match_actor,
                                    r.match_ip, r.action, r.keep_days, r.request_body, r.response_body) for r in rows]
            except Exception:
                logger.debug("activity rules: load failed; keeping the previous set", exc_info=True)
            self._loaded_at = time.monotonic()
        return self._rules

    async def match(self, **request: Any) -> Rule | None:
        for rule in await self.rules():
            if rule.matches(**request):
                return rule
        return None

    def count_hit(self, rule: Rule, ip: str | None) -> None:
        entry = self._hits.setdefault(rule.id, [0, None, None])
        entry[0] += 1
        entry[1] = utc_now()
        entry[2] = ip

    def take_hits(self) -> dict[int, tuple[int, datetime, str | None]]:
        hits, self._hits = self._hits, {}
        return {k: (v[0], v[1], v[2]) for k, v in hits.items()}


_cache: RuleCache | None = None


def get_rule_cache() -> RuleCache:
    global _cache
    if _cache is None:
        _cache = RuleCache()
    return _cache


def reset_rule_cache_for_tests() -> None:
    global _cache
    _cache = None
