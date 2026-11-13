"""Unit tests for the transactional-outbox state helpers (audit A01)."""
from __future__ import annotations

from datetime import datetime

from app.core import outbox
from app.db.models import Delivery, DeliveryState, DeliveryStatus


def _d(**kw):
    kw.setdefault("notification_id", "n1")
    kw.setdefault("channel", "ui")
    kw.setdefault("state", DeliveryState.pending)
    kw.setdefault("attempts", 0)
    kw.setdefault("idempotency_key", "n1:ui")
    return Delivery(**kw)


def test_backoff_is_exponential_and_capped():
    assert outbox.backoff_seconds(1) == 30
    assert outbox.backoff_seconds(2) == 60
    assert outbox.backoff_seconds(3) == 120
    assert outbox.backoff_seconds(99) == 3600  # capped


def test_apply_attempt_success_marks_sent():
    d = _d()
    outbox.apply_attempt(d, ok=True, now=datetime(2026, 1, 1))
    assert d.state == DeliveryState.sent
    assert d.attempts == 1
    assert d.next_attempt_at is None
    assert d.last_error is None


def test_apply_attempt_retryable_stays_pending_with_backoff():
    d = _d()
    now = datetime(2026, 1, 1, 0, 0, 0)
    outbox.apply_attempt(d, ok=False, error="sink 503", now=now)
    assert d.state == DeliveryState.pending
    assert d.attempts == 1
    assert d.next_attempt_at is not None and d.next_attempt_at > now
    assert "503" in d.last_error


def test_apply_attempt_permanent_fails_immediately():
    d = _d()
    outbox.apply_attempt(d, ok=False, error="channel disabled")
    assert d.state == DeliveryState.failed
    assert d.next_attempt_at is None


def test_apply_attempt_exhausts_retries_to_failed():
    d = _d(attempts=outbox.MAX_ATTEMPTS - 1)
    outbox.apply_attempt(d, ok=False, error="sink 503")
    assert d.attempts == outbox.MAX_ATTEMPTS
    assert d.state == DeliveryState.failed
    assert d.next_attempt_at is None


def test_apply_deferral_reschedules_without_counting_an_attempt():
    # F22: a circuit-open / rate-limited denial never reached the transport,
    # so it must NOT burn a retry attempt — it reschedules and stays pending.
    now = datetime(2026, 1, 1, 0, 0, 0)
    d = _d(attempts=4, created_at=now)  # one short of MAX_ATTEMPTS
    outbox.apply_deferral(d, reason="circuit_open", now=now)
    assert d.attempts == 4  # unchanged
    assert d.state == DeliveryState.pending
    assert d.next_attempt_at is not None
    assert d.next_attempt_at > now
    assert "deferred" in d.last_error
    assert "circuit_open" in d.last_error


def test_apply_deferral_fails_once_delivery_too_old():
    # Expiry is bounded by delivery AGE, not attempts (F22).
    from datetime import timedelta
    created = datetime(2026, 1, 1, 0, 0, 0)
    now = created + timedelta(seconds=outbox.MAX_DELIVERY_AGE_SEC + 1)
    d = _d(attempts=0, created_at=created)
    outbox.apply_deferral(d, reason="rate_limited", now=now)
    assert d.state == DeliveryState.failed
    assert d.next_attempt_at is None


def test_rollup_pending_when_any_pending():
    ds = [_d(state=DeliveryState.sent), _d(state=DeliveryState.pending)]
    assert outbox.rollup_status(ds) == DeliveryStatus.pending


def test_rollup_partial_when_sent_and_failed():
    ds = [_d(state=DeliveryState.sent), _d(state=DeliveryState.failed)]
    assert outbox.rollup_status(ds) == DeliveryStatus.partial


def test_rollup_sent_when_all_sent():
    assert outbox.rollup_status([_d(state=DeliveryState.sent)]) == DeliveryStatus.sent


def test_rollup_failed_when_all_failed():
    assert outbox.rollup_status([_d(state=DeliveryState.failed)]) == DeliveryStatus.failed
