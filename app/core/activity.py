"""Activity log: delivery attempts, API requests, system events.

Design and policy: docs/ACTIVITY_LOG.md. Three pieces:

- **Exchange recorder** — ``capture_exchanges()`` opens a per-task list that
  ``note_exchange()`` (called by ``safe_request`` and the Telegram client)
  appends every outbound HTTP request/response to. The channel manager wraps
  each ``adapter.send()`` in it, so HTTP providers need no code of their own.
- **Redaction** — ``redact_body()``: secret-looking JSON keys masked, URLs
  through ``redact_url``, trimmed. Headers are never recorded except a short
  allowlist of response headers.
- **Writer** — ``submit()`` puts a row on a bounded queue and returns at
  once; a background task inserts batches (every second or 100 rows) in its
  own transaction. Recording never blocks or fails a request or a send: a full
  queue drops the row and counts it.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Iterator
from contextvars import ContextVar
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, quote_plus

from ..config import get_settings
from ..secrets_registry import SECRET_FIELDS
from ..utils.redact import collapse_urls, redact_url, safe_url_display
from ..utils.time import utc_now

logger = logging.getLogger(__name__)

EXCHANGE_BODY_LIMIT = 4096
FIRE_BODY_LIMIT = 4096
WEBHOOK_BODY_LIMIT = 65536
ERROR_RESPONSE_LIMIT = 2048
_MAX_EXCHANGES = 10
_BATCH = 100
_FLUSH_EVERY_SEC = 1.0
# Response headers worth keeping; request headers are never recorded.
KEPT_RESPONSE_HEADERS = ("content-type", "retry-after", "idempotent-replayed")
_SECRET_KEY_MARKERS = ("password", "passwd", "token", "secret", "api_key", "apikey", "auth_value",
                       "authorization", "private", "credential", "cookie")

# ── Redaction ──────────────────────────────────────────────────────


# Every literal secret field a channel or input kind declares (``user_key``,
# ``username`` … do not contain a marker word).
_REGISTERED_SECRET_KEYS = frozenset(
    name for kinds in SECRET_FIELDS.values() for names in kinds.values() for name in names)
# Form fields that carry a credential under a generic name (Pushover: ``user``).
_FORM_SECRET_KEYS = frozenset({"user"})


def _secret_key(key: str) -> bool:
    k = key.lower()
    return not k.endswith("_ref") and (k in _REGISTERED_SECRET_KEYS or any(m in k for m in _SECRET_KEY_MARKERS))


def _mask(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            if _secret_key(str(k)):
                out[k] = "<redacted>"
            elif str(k).lower() == "headers" and isinstance(v, dict):
                # Custom headers are where API keys go (DD-API-KEY, X-Gotify-Key …):
                # the names help, the values never do.
                out[k] = dict.fromkeys(v, "<redacted>")
            else:
                out[k] = _mask(v)
        return out
    if isinstance(value, list):
        return [_mask(v) for v in value]
    if isinstance(value, str) and "://" in value:
        return redact_url(value)
    return value


def trim(text: str, limit: int) -> str:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    cut = data[:limit].decode("utf-8", errors="ignore")
    return f"{cut}…[{len(data) - limit} more bytes]"


def _mask_form(text: str) -> str | None:
    """``a=1&token=s`` with its secret values masked, or None when ``text`` is
    not a form body. Providers that take a form (Pushover) put their
    credentials in it, where neither JSON keys nor URL rules apply."""
    if "=" not in text or any(c.isspace() for c in text):
        return None
    try:
        pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    return "&".join(
        f"{quote_plus(k)}=" + ("<redacted>" if _secret_key(k) or k.lower() in _FORM_SECRET_KEYS else quote_plus(v))
        for k, v in pairs)


def redact_body(body: Any, limit: int) -> str | None:
    """A body fit to store: JSON with secret keys masked, else redacted text."""
    if body is None or body == b"" or body == "":
        return None
    if isinstance(body, bytes | bytearray):
        try:
            text = bytes(body).decode("utf-8")
        except UnicodeDecodeError:
            # Encrypted (Web Push) or other binary content: its size is what helps.
            return f"[binary, {len(body)} bytes]"
    elif isinstance(body, dict | list):
        text = json.dumps(body, ensure_ascii=False, default=str)
    else:
        text = str(body)
    try:
        parsed = json.loads(text)
    except ValueError:
        return trim(_mask_form(text) or redact_url(text), limit)
    return trim(json.dumps(_mask(parsed), ensure_ascii=False, default=str), limit)


# ── Exchange recorder ──────────────────────────────────────────────

_exchanges: ContextVar[list[dict[str, Any]] | None] = ContextVar("klopot_exchanges", default=None)


@contextlib.contextmanager
def capture_exchanges() -> Iterator[list[dict[str, Any]]]:
    """Collect the outbound HTTP exchanges made inside the block."""
    bucket: list[dict[str, Any]] = []
    token = _exchanges.set(bucket)
    try:
        yield bucket
    finally:
        _exchanges.reset(token)


def note_exchange(
    *, method: str, url: str, status: int | None, duration_ms: int,
    request_body: Any = None, response_body: Any = None,
    response_headers: Any = None, error: str | None = None, url_is_masked: bool = False,
) -> None:
    """Record one outbound request in the open recorder (no-op outside one).

    The URL is kept as ``scheme://host/…``: a destination path can itself be
    the credential (Slack, Discord, Home Assistant webhook ids, an ntfy topic)
    and nothing tells such a segment from a harmless one. A caller that has
    already masked its URL (Telegram) says so with ``url_is_masked``."""
    bucket = _exchanges.get()
    if bucket is None or len(bucket) >= _MAX_EXCHANGES:
        return
    bodies = get_settings().activity_log_bodies
    headers = {}
    if response_headers is not None:
        for name in KEPT_RESPONSE_HEADERS:
            v = response_headers.get(name) if hasattr(response_headers, "get") else None
            if v:
                headers[name] = str(v)[:200]
    bucket.append({
        "method": method.upper(), "url": (redact_url(url) if url_is_masked else safe_url_display(url))[:500], "status": status, "duration_ms": duration_ms,
        "request_body": redact_body(request_body, EXCHANGE_BODY_LIMIT) if bodies else None,
        "response_body": redact_body(response_body, EXCHANGE_BODY_LIMIT) if bodies else None,
        "response_headers": headers or None,
        "error": collapse_urls(error)[:300] if error else None,
    })


# ── Writer ─────────────────────────────────────────────────────────


# MySQL deadlock / lock wait timeout: the transaction was rolled back whole.
_TRANSIENT_CODES = {1213, 1205}
_WRITE_ATTEMPTS = 3
_RETRY_BACKOFF_SEC = 0.2


def _code(e: BaseException) -> int | None:
    orig = getattr(e, "orig", None)
    args = getattr(orig, "args", None) or ()
    return args[0] if args and isinstance(args[0], int) else None


def _transient(e: BaseException) -> bool:
    return _code(e) in _TRANSIENT_CODES


class ActivityWriter:
    """Bounded queue + batching background inserts (one per process)."""

    def __init__(self, max_queue: int = 5000):
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] | None = None
        self._max_queue = max_queue
        self._task: asyncio.Task[None] | None = None
        self.dropped = 0

    def _q(self) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._max_queue)
        return self._queue

    def submit(self, table: str, row: dict[str, Any]) -> None:
        try:
            self._q().put_nowait((table, row))
        except asyncio.QueueFull:
            self.dropped += 1
            from ..metrics import ACTIVITY_DROPPED_TOTAL
            ACTIVITY_DROPPED_TOTAL.inc()

    async def flush(self, limit: int | None = None) -> int:
        """Insert what is queued now (up to ``limit``); returns rows written."""
        from ..db.models import ApiRequest, DeliveryAttempt, SystemEvent
        from ..db.session import get_session_factory

        models = {"attempt": DeliveryAttempt, "request": ApiRequest, "event": SystemEvent}
        from .activity_rules import get_rule_cache

        q = self._q()
        batch: list[tuple[str, dict[str, Any]]] = []
        while not q.empty() and (limit is None or len(batch) < limit):
            batch.append(q.get_nowait())
        hits = get_rule_cache().take_hits()
        if not batch and not hits:
            return 0
        for attempt in range(1, _WRITE_ATTEMPTS + 1):
            try:
                async with get_session_factory()() as session:
                    session.add_all([models[table](**row) for table, row in batch])
                    for rule_id, (count, last_at, last_ip) in hits.items():
                        from sqlalchemy import update

                        from ..db.models import ActivityRule
                        await session.execute(update(ActivityRule).where(ActivityRule.id == rule_id).values(
                            hits=ActivityRule.hits + count, last_hit_at=last_at, last_ip=(last_ip or "")[:45] or None))
                    await session.commit()
                return len(batch)
            except Exception as e:
                # A deadlock or lock wait is transient: the whole transaction
                # was rolled back, so writing it again cannot duplicate a row
                # (rc.9 review RC-01: a 1213 lost a batch, uncounted).
                if attempt < _WRITE_ATTEMPTS and _transient(e):
                    logger.warning("activity log: %s writing %d row(s), retrying (%d/%d)",
                                   _code(e) or type(e).__name__, len(batch), attempt, _WRITE_ATTEMPTS)
                    await asyncio.sleep(_RETRY_BACKOFF_SEC * attempt)
                    continue
                # The log must never take the service down: drop the rows,
                # count them, keep the rule counters for the next flush.
                logger.exception("activity log: could not write %d row(s)", len(batch))
                get_rule_cache().give_back_hits(hits)
                if batch:
                    self.dropped += len(batch)
                    from ..metrics import ACTIVITY_DROPPED_TOTAL
                    ACTIVITY_DROPPED_TOTAL.inc(len(batch))
                return 0
        return 0  # pragma: no cover — the loop always returns

    async def _run(self) -> None:
        # Every second, whether rows are queued or not: an ``ignore`` rule only
        # bumps an in-memory counter (nothing is queued), and those counters
        # must still reach the table. With nothing to do, flush() returns
        # without touching the database.
        while True:
            await asyncio.sleep(_FLUSH_EVERY_SEC)
            try:
                while await self.flush(limit=_BATCH) == _BATCH:
                    pass
            except Exception:  # never let the writer die
                logger.exception("activity log: writer tick failed")

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="activity-writer")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        with contextlib.suppress(Exception):
            await self.flush()


_writer: ActivityWriter | None = None


def get_activity_writer() -> ActivityWriter:
    global _writer
    if _writer is None:
        _writer = ActivityWriter(max_queue=get_settings().activity_queue_max)
    return _writer


def reset_activity_writer_for_tests() -> None:
    global _writer
    _writer = None


# ── Record helpers (what the call sites use) ───────────────────────


def record_attempt(
    *, channel: str, kind: str, outcome: str, started_at: datetime, duration_ms: int,
    exchange: list[dict[str, Any]] | None, delivery_id: int | None = None,
    notification_id: str | None = None, attempt_no: int = 1, error: str | None = None,
    retry_after: float | None = None, provider_ref: str | None = None,
) -> None:
    http_status = next((e["status"] for e in reversed(exchange or []) if e.get("status")), None)
    get_activity_writer().submit("attempt", {
        "delivery_id": delivery_id, "notification_id": notification_id, "channel": channel[:64],
        "kind": kind, "attempt_no": attempt_no, "started_at": started_at, "duration_ms": duration_ms,
        "outcome": outcome, "http_status": http_status,
        "retry_after_sec": int(retry_after) if retry_after is not None else None,
        "provider_ref": (provider_ref or None) and str(provider_ref)[:255],
        "error": redact_url(error)[:500] if error else None, "exchange": exchange or None,
    })


def record_event(*, source_kind: str, source_name: str, event: str,
                 source_id: int | None = None, detail: str | None = None) -> None:
    get_activity_writer().submit("event", {
        "ts": utc_now(), "source_kind": source_kind, "source_id": source_id,
        "source_name": source_name[:128], "event": event[:32],
        "detail": redact_url(detail)[:500] if detail else None,
    })


def record_request(row: dict[str, Any]) -> None:
    get_activity_writer().submit("request", row)
