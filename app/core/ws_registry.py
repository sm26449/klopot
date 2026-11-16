"""Live WebSocket connection registry (audit A07).

WebSockets authenticate once at handshake; without a registry a logged-
out or revoked session keeps streaming until the client hangs up. This
process-local registry tracks every open stream by its auth identity
(session / user / api-key) so the revoke paths can close it IMMEDIATELY.

alertd runs a single uvicorn worker (Dockerfile ``--workers 1``), so one
process holds every connection and this registry is authoritative. The
stream handlers add a periodic re-validation as a backstop for idle
*expiry* (which fires no revoke event) — see ``app/api/v1/state.py``.

It also bounds them (review F14): each stream holds a queue and costs a
JSON encode per update, and nothing capped how many one caller opened.
``register`` refuses past ``MAX_PER_IDENTITY`` for one session or API key and
past ``MAX_TOTAL`` altogether; the handlers register before accepting, so a
refused stream is closed (1013, try again later) without being served.

Dependency-free on purpose (no app imports) so ``auth`` can call it
without an import cycle.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Open streams one session or API key may hold (a few tabs, each with its
# notification and state streams), and the process altogether.
MAX_PER_IDENTITY = 10
MAX_TOTAL = 500


class StreamLimitReached(Exception):
    """No room for another stream; the message says which limit."""


@dataclass
class _Entry:
    ws: Any
    session_id: int | None
    user_id: int | None
    key_id: int | None


class WSRegistry:
    """Tracks open WebSocket streams and closes them on demand.

    Not thread-safe by lock — a single-worker asyncio app touches it only
    from the event-loop thread. Closes are scheduled as tasks so a sync
    caller (the auth cache invalidators) can trigger them.
    """

    def __init__(self) -> None:
        self._conns: dict[int, _Entry] = {}
        self._ids = itertools.count(1)

    def register(
        self,
        ws: Any,
        *,
        session_id: int | None = None,
        user_id: int | None = None,
        key_id: int | None = None,
    ) -> int:
        """Track ``ws``; raise ``StreamLimitReached`` when its session or key
        already holds ``MAX_PER_IDENTITY`` streams, or the process ``MAX_TOTAL``."""
        if len(self._conns) >= MAX_TOTAL:
            raise StreamLimitReached(f"at most {MAX_TOTAL} live streams")
        if session_id is not None or key_id is not None:
            mine = sum(1 for e in self._conns.values()
                       if (session_id is not None and e.session_id == session_id)
                       or (key_id is not None and e.key_id == key_id))
            if mine >= MAX_PER_IDENTITY:
                raise StreamLimitReached(f"at most {MAX_PER_IDENTITY} live streams per session or key")
        handle = next(self._ids)
        self._conns[handle] = _Entry(ws, session_id, user_id, key_id)
        return handle

    def unregister(self, handle: int) -> None:
        self._conns.pop(handle, None)

    def _close_where(self, pred: Callable[[_Entry], bool], reason: str) -> int:
        victims = [h for h, e in self._conns.items() if pred(e)]
        for h in victims:
            entry = self._conns.pop(h, None)
            if entry is not None:
                _schedule_close(entry.ws, reason)
        if victims:
            logger.info("ws_registry: closing %d stream(s) — %s", len(victims), reason)
        return len(victims)

    def close_session(self, session_id: int) -> int:
        return self._close_where(lambda e: e.session_id == session_id, "session revoked")

    def close_user(self, user_id: int) -> int:
        return self._close_where(lambda e: e.user_id == user_id, "user sessions revoked")

    def close_key(self, key_id: int) -> int:
        return self._close_where(lambda e: e.key_id == key_id, "api key revoked")

    def close_all_sessions(self) -> int:
        return self._close_where(lambda e: e.session_id is not None, "all sessions revoked")

    def close_all_keys(self) -> int:
        return self._close_where(lambda e: e.key_id is not None, "all keys revoked")

    def __len__(self) -> int:  # pragma: no cover - introspection only
        return len(self._conns)


# Hold strong references to in-flight close tasks so they are not
# garbage-collected before they run (ruff RUF006).
_pending_closes: set[asyncio.Task[None]] = set()


def _schedule_close(ws: Any, reason: str) -> None:
    """Close ``ws`` on the running event loop. The invalidators are sync
    but run inside async request handlers, so a loop is available; if not
    (e.g. a CLI process), there is nothing of ours to close here."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - no loop (CLI); registry is empty anyway
        return
    task = loop.create_task(_safe_close(ws, reason))
    _pending_closes.add(task)
    task.add_done_callback(_pending_closes.discard)


async def _safe_close(ws: Any, reason: str) -> None:
    from fastapi import status

    try:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason[:120])
    except Exception:  # pragma: no cover - already closing / closed
        pass


_registry: WSRegistry | None = None


def get_ws_registry() -> WSRegistry:
    global _registry
    if _registry is None:
        _registry = WSRegistry()
    return _registry
