"""Prometheus metrics for alertd.

S12 — surface enough operational signal for a Prometheus scrape +
Grafana dashboard so we can answer the typical questions:

- Is the engine still firing rules? (rate of fires_total)
- Are dispatches landing? (dispatch_latency, suppressed counter)
- Are channels healthy? (breaker_state)
- Is MQTT lagging? (input_msg_lag_sec)
- How big is the log table? (log_table_rows)

Metric naming follows the project prefix `alertd_` so a single
Prometheus instance can host many services without conflict.

Usage in code::

    from app.metrics import FIRES_TOTAL, DISPATCH_LATENCY_MS
    FIRES_TOTAL.labels(type="soc_low", severity="warning",
                       suppressed="false").inc()
    DISPATCH_LATENCY_MS.labels(channel="ui").observe(42.0)

The /v1/metrics endpoint exposes the registry in Prometheus
exposition format. No auth — Prometheus scrapes from inside the
docker network. Add an L7 ACL at the proxy if exposing publicly.
"""
from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry()


# ── Engine fires ──────────────────────────────────────────────────

FIRES_TOTAL = Counter(
    "alertd_fires_total",
    "Total notification fires emitted by the engine + manual /v1/fire calls.",
    ["type", "severity", "suppressed"],
    registry=REGISTRY,
)

ESCALATIONS_TOTAL = Counter(
    "alertd_escalations_total",
    "Unacked criticals re-paged through the escalation channel.",
    ["channel", "outcome"],
    registry=REGISTRY,
)

RULE_EVAL_DURATION_MS = Histogram(
    "alertd_rule_eval_duration_ms",
    "Time spent evaluating a single rule condition expression.",
    ["rule_id"],
    buckets=(0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000),
    registry=REGISTRY,
)

RULE_EVAL_ERRORS_TOTAL = Counter(
    "alertd_rule_eval_errors_total",
    "Rule expression evaluation failures (typo, missing var, type error, etc).",
    ["rule_id"],
    registry=REGISTRY,
)


# ── Channel dispatch ──────────────────────────────────────────────

DISPATCH_LATENCY_MS = Histogram(
    "alertd_dispatch_latency_ms",
    "End-to-end channel send latency (from dispatch start to channel ack).",
    ["channel"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
    registry=REGISTRY,
)

DISPATCH_FAILURES_TOTAL = Counter(
    "alertd_dispatch_failures_total",
    "Failed channel sends, by channel and short error class.",
    ["channel", "reason"],
    registry=REGISTRY,
)

CHANNEL_BREAKER_STATE = Gauge(
    "alertd_channel_breaker_state",
    "Circuit breaker state. 0=closed (healthy), 1=half_open, 2=open.",
    ["channel"],
    registry=REGISTRY,
)


# ── Inputs ────────────────────────────────────────────────────────

INPUT_MSG_LAG_SEC = Gauge(
    "alertd_input_msg_lag_sec",
    "Seconds since the last message from this input (0 if recent).",
    ["input"],
    registry=REGISTRY,
)

INPUT_CONNECTED = Gauge(
    "alertd_input_connected",
    "1 if the input adapter reports connected, else 0.",
    ["input"],
    registry=REGISTRY,
)


# ── Storage ───────────────────────────────────────────────────────

LOG_TABLE_ROWS = Gauge(
    "alertd_log_table_rows",
    "Approximate row count of the notifications_log table.",
    registry=REGISTRY,
)


AGGREGATE_OVERFLOW = Gauge(
    "alertd_aggregate_overflow",
    "Number of aggregate variables currently over their member budget and "
    "holding an invalidated output (audit D1-01).",
    registry=REGISTRY,
)


# ── Retention ─────────────────────────────────────────────────────
#
# The hourly retention sweep is logged via the structured logger, but
# the audit (2026-05-11 O-2) found that INFO logs from modules below
# `app.main` get silently dropped — making it impossible to verify the
# sweep is actually running. Surface it through Prometheus instead:
# a counter (so absence is detectable as a flat rate-over-time) and a
# timestamp gauge (so a Grafana "stale > 2h" alert is one click away).
#
RETENTION_RUNS_TOTAL = Counter(
    "alertd_retention_runs_total",
    "Total retention sweep runs, by outcome.",
    ["result"],  # success | error
    registry=REGISTRY,
)

RETENTION_ROWS_DELETED_TOTAL = Counter(
    "alertd_retention_rows_deleted_total",
    "Rows deleted by retention sweep, by table.",
    ["table"],  # notifications_log | audit_log
    registry=REGISTRY,
)

RETENTION_LAST_RUN_TS = Gauge(
    "alertd_retention_last_run_timestamp",
    "Unix timestamp of the last retention sweep (any outcome).",
    registry=REGISTRY,
)


# ── Helpers ───────────────────────────────────────────────────────


def render_latest() -> tuple[bytes, str]:
    """Return (body, content_type) for the /v1/metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


_BREAKER_STATE_MAP = {"closed": 0, "half_open": 1, "open": 2}


def set_breaker_state(channel: str, state: str) -> None:
    val = _BREAKER_STATE_MAP.get(state, 0)
    CHANNEL_BREAKER_STATE.labels(channel=channel).set(val)
