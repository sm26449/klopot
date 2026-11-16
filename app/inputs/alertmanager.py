"""Alertmanager / Grafana receiver — ``kind: alertmanager``.

Prometheus Alertmanager (webhook_config, payload v4) and Grafana unified
alerting (webhook contact point) POST a *group* of alerts to
``POST /v1/inputs/{id}/webhook``. Each alert becomes an external episode
(see ``app/core/fire_service.py``): ``firing`` opens it and notifies once,
re-sends of the same alert notify nothing, ``resolved`` closes it.

This module holds the input adapter (auth + health, shared with the plain
webhook input) and the **pure** parsing / mapping functions; the database
side lives in ``app/services/alertmanager.py``.

Config:

- ``default_type`` (required): template for an alert no rule below matches —
  unknown alert names are never dropped.
- ``type_label`` (default ``alertname``) and ``label_types``: the template
  named by that label's value, if it exists and ``label_types`` allows it
  (exact names or patterns like ``am_*``). Empty ``label_types`` = the label
  picks nothing — whoever holds the token cannot choose any template, say
  one that pages by SMS (public-exposure review).
- ``type_by_severity``: ``{"critical": "am_critical", "default": "am_info"}``
  — template by ``labels.severity`` when ``type_label`` gave no template.
- ``resolved_type``: template for the resolution notice (optional).
- ``max_alerts`` (default 200, at most 1000): alerts processed per request;
  the rest are counted as truncated, like Alertmanager's own
  ``truncatedAlerts``.
- ``max_new_episodes_per_min`` (default 60) and ``max_active_episodes``
  (default 500): what one input may open. A firing alert past either is not
  opened (``over_budget``); Alertmanager sends it again while it fires. Each
  new fingerprint is an episode and a notification, so without these one
  request could enqueue hundreds of them.
- ``auth_token`` / ``auth_token_ref`` + ``auth_required``: as for webhook
  inputs; the token may arrive as ``X-Input-Token`` or
  ``Authorization: Bearer <token>`` (Alertmanager's ``http_config``).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from typing import Any, TypeGuard

from ..utils.keys import bounded_key
from .webhook import WebhookInput

TRUNCATED_TYPE = "alertmanager_truncated"
DEFAULT_TYPE = "alertmanager_alert"
MAX_LABEL_TYPES = 100

# name → (default, smallest, largest): the budgets an input may set.
LIMITS: dict[str, tuple[int, int, int]] = {
    "max_alerts": (200, 1, 1000),
    "max_new_episodes_per_min": (60, 1, 10_000),
    "max_active_episodes": (500, 1, 100_000),
}
DEFAULT_MAX_ALERTS = LIMITS["max_alerts"][0]


def _whole(value: Any) -> TypeGuard[int]:
    """A whole number — not a bool, which Python counts as one."""
    return isinstance(value, int) and not isinstance(value, bool)


def limit(config: dict[str, Any], name: str) -> int:
    """The input's ``name`` budget: its configured value within the bounds,
    else the default (a stored config is validated on save; this is the
    guarantee for one that was not)."""
    default, low, high = LIMITS[name]
    value = config.get(name)
    return min(max(value, low), high) if _whole(value) else default


def validate_config(config: dict[str, Any]) -> None:
    """Refuse budgets outside their bounds and a malformed ``label_types``
    (``ValueError`` with the fix)."""
    for name, (_default, low, high) in LIMITS.items():
        value = config.get(name)
        if value is not None and not (_whole(value) and low <= value <= high):
            raise ValueError(f"{name} must be a whole number from {low} to {high}, or empty for {_default}")
    types = config.get("label_types")
    if types is not None and not (
        isinstance(types, list) and len(types) <= MAX_LABEL_TYPES
        and all(isinstance(t, str) and t.strip() for t in types)
    ):
        raise ValueError(f"label_types must be a list of template names or patterns (am_*), at most {MAX_LABEL_TYPES}")


class AlertmanagerInput(WebhookInput):
    """Passive receiver: auth and health come from the webhook input."""

    kind = "alertmanager"

    @classmethod
    def validate_config(cls, config: dict[str, Any], *, before: dict[str, Any] | None = None) -> None:
        super().validate_config(config, before=before)
        validate_config(config)

    def health(self) -> dict[str, Any]:
        out = super().health()
        out["kind"] = self.kind
        return out


@dataclass
class Alert:
    status: str                       # firing | resolved
    labels: dict[str, str]
    annotations: dict[str, str]
    starts_at: datetime | None
    ends_at: datetime | None
    fingerprint: str
    generator_url: str | None


@dataclass
class Group:
    alerts: list[Alert]
    truncated: int = 0                # dropped by the sender or by max_alerts
    common: dict[str, Any] = field(default_factory=dict)   # receiver, groupKey, externalURL …
    errors: list[str] = field(default_factory=list)


def parse_time(value: Any) -> datetime | None:
    """RFC 3339 → naive UTC. Alertmanager sends nanoseconds and uses
    ``0001-01-01T00:00:00Z`` for "not set"; both are handled."""
    if not isinstance(value, str) or not value or value.startswith("0001-01-01"):
        return None
    text = value.strip().replace("Z", "+00:00")
    if "." in text:   # trim fractional seconds to microseconds
        head, _, tail = text.partition(".")
        digits = "".join(c for c in tail if c.isdigit())
        rest = tail[len(digits):]
        text = f"{head}.{digits[:6].ljust(6, '0')}{rest}"
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        return None
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    return ts


def _strings(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _fingerprint(labels: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(labels, sort_keys=True).encode()).hexdigest()[:16]


def parse_group(payload: Any, *, max_alerts: int = DEFAULT_MAX_ALERTS) -> Group:
    """Validate and normalise an Alertmanager v4 / Grafana webhook body."""
    if not isinstance(payload, dict) or not isinstance(payload.get("alerts"), list):
        return Group(alerts=[], errors=["body must be an Alertmanager webhook payload with an 'alerts' list"])
    raw = payload["alerts"]
    sent_truncated = payload.get("truncatedAlerts")
    truncated: int = sent_truncated if isinstance(sent_truncated, int) and sent_truncated > 0 else 0
    if len(raw) > max_alerts:
        truncated += len(raw) - max_alerts
        raw = raw[:max_alerts]
    alerts: list[Alert] = []
    errors: list[str] = []
    for i, a in enumerate(raw):
        if not isinstance(a, dict):
            errors.append(f"alerts[{i}] is not an object")
            continue
        labels = _strings(a.get("labels"))
        status = a.get("status") or payload.get("status") or "firing"
        if status not in ("firing", "resolved"):
            errors.append(f"alerts[{i}]: unknown status {status!r}")
            continue
        alerts.append(Alert(
            status=status, labels=labels, annotations=_strings(a.get("annotations")),
            starts_at=parse_time(a.get("startsAt")), ends_at=parse_time(a.get("endsAt")),
            fingerprint=str(a.get("fingerprint") or _fingerprint(labels)),
            generator_url=a.get("generatorURL") if isinstance(a.get("generatorURL"), str) else None,
        ))
    common = {k: payload.get(k) for k in ("receiver", "groupKey", "externalURL") if isinstance(payload.get(k), str)}
    return Group(alerts=alerts, truncated=truncated, common=common, errors=errors)


def choose_type(alert: Alert, config: dict[str, Any], templates: set[str]) -> str:
    """Template for an alert: its type label if such a template exists and
    ``label_types`` allows it, else by severity, else ``default_type`` (never
    dropped). The sender's labels choose only among the templates the
    operator listed."""
    by_label = alert.labels.get(config.get("type_label") or "alertname")
    allowed = config.get("label_types") or []
    if by_label and by_label in templates and any(fnmatchcase(by_label, p) for p in allowed if isinstance(p, str)):
        return by_label
    by_sev = config.get("type_by_severity") or {}
    if isinstance(by_sev, dict):
        for key in (alert.labels.get("severity"), "default"):
            candidate = by_sev.get(key) if key else None
            if isinstance(candidate, str) and candidate in templates:
                return candidate
    return str(config.get("default_type") or DEFAULT_TYPE)


def alert_context(alert: Alert, common: dict[str, Any]) -> dict[str, Any]:
    """Template context: nested ``labels`` / ``annotations`` plus flat dotted
    keys (``{labels.instance}``, ``{annotations.summary}``)."""
    ctx: dict[str, Any] = {
        "status": alert.status,
        "labels": dict(alert.labels),
        "annotations": dict(alert.annotations),
        "alert": {
            "fingerprint": alert.fingerprint,
            "starts_at": alert.starts_at.isoformat() + "Z" if alert.starts_at else None,
            "ends_at": alert.ends_at.isoformat() + "Z" if alert.ends_at else None,
            "generator_url": alert.generator_url,
        },
        **{f"am.{k}": v for k, v in common.items()},
    }
    ctx.update({f"labels.{k}": v for k, v in alert.labels.items()})
    ctx.update({f"annotations.{k}": v for k, v in alert.annotations.items()})
    return ctx


def episode_prefix(input_id: int) -> str:
    """The start of every episode key of an input — kept whole by
    ``bounded_key``, so an input's active episodes are one index range."""
    return f"am:{input_id}:"


def episode_key(input_id: int, alert: Alert) -> str:
    # The fingerprint comes from the sender and has no length limit of its own.
    return bounded_key(episode_prefix(input_id) + alert.fingerprint)


def episode_name(alert: Alert) -> str:
    return alert.labels.get("alertname") or alert.fingerprint
