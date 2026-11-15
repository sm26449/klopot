"""``/v1/activity`` — the activity log (docs/ACTIVITY_LOG.md).

Requests Klopot received, attempts it made to providers, state changes of
inputs / rules / channels, and the rules that decide what the request log
keeps. Metadata needs ``read``; request / response bodies need ``admin``
(alert text and payloads can carry personal data).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import model_to_dict, record_change
from ...auth import Actor, require_scope
from ...core.activity_rules import Rule, get_rule_cache
from ...db.models import ActivityRule, ApiRequest, DeliveryAttempt, SystemEvent
from ...db.session import get_session
from ...schemas.activity import (
    ActivityRuleCreate,
    ActivityRuleRead,
    ActivityRuleUpdate,
    ApiRequestDetail,
    ApiRequestRead,
    AttemptRead,
    IgnoredRow,
    RulePreview,
    SourceRow,
    SourcesResponse,
    SystemEventRead,
)
from ...schemas.common import Page
from ...schemas.log import _as_utc_iso
from ...utils.like import LIKE_ESCAPE, like_escape
from ...utils.redact import collapse_urls, is_redacted_url_display, safe_url_display
from ...utils.time import utc_now

router = APIRouter()


def _status_filter(status_class: str | None) -> Any:
    if not status_class:
        return None
    s = status_class.lower()
    if s in ("1xx", "2xx", "3xx", "4xx", "5xx"):
        lo = int(s[0]) * 100
        return (ApiRequest.status >= lo) & (ApiRequest.status < lo + 100)
    if s.isdigit():
        return ApiRequest.status == int(s)
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="status: a class like 4xx or a code")


def _request_read(r: ApiRequest) -> ApiRequestRead:
    return ApiRequestRead.model_validate({**{c: getattr(r, c) for c in ApiRequestRead.model_fields
                                            if hasattr(r, c)},
                                          "has_request_body": bool(r.request_body),
                                          "has_response_body": bool(r.response_body)})


# ── Requests ───────────────────────────────────────────────────────


@router.get("/requests", response_model=Page[ApiRequestRead], summary="Requests Klopot received")
async def list_requests(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    method: str | None = None,
    route: str | None = Query(default=None, description="Exact route template, e.g. /v1/fire"),
    search: str | None = Query(default=None, description="Substring of the path"),
    status_class: str | None = Query(default=None, alias="status", description="2xx, 4xx… or a code"),
    actor: str | None = None,
    ip: str | None = None,
    trace_id: str | None = None,
    webhooks: bool = Query(default=False, description="Only inbound webhook / Alertmanager / SMS-inbox requests"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
    _actor: Actor = Depends(require_scope("read")),
) -> Page[ApiRequestRead]:
    filters: list[Any] = []
    if method:
        filters.append(ApiRequest.method == method.upper())
    if route:
        filters.append(ApiRequest.route == route)
    if search:
        filters.append(ApiRequest.path.like(f"%{like_escape(search)}%", escape=LIKE_ESCAPE))
    if (sf := _status_filter(status_class)) is not None:
        filters.append(sf)
    if actor:
        filters.append(ApiRequest.actor_name == actor)
    if ip:
        filters.append(ApiRequest.client_ip == ip)
    if trace_id:
        filters.append(ApiRequest.trace_id == trace_id)
    if webhooks:
        filters.append(ApiRequest.route == "/v1/inputs/{input_id}/webhook")
    if from_:
        filters.append(ApiRequest.ts >= from_)
    if to:
        filters.append(ApiRequest.ts <= to)
    total = (await session.execute(select(func.count()).select_from(ApiRequest).where(*filters))).scalar_one()
    rows = (await session.execute(select(ApiRequest).where(*filters)
                                  .order_by(ApiRequest.ts.desc(), ApiRequest.id.desc()).offset(skip).limit(limit))).scalars().all()
    return Page(items=[_request_read(r) for r in rows], total=total, limit=limit, offset=skip)


@router.get("/requests/{request_id}", response_model=ApiRequestDetail, summary="One request, with its bodies")
async def get_request(
    request_id: int,
    session: AsyncSession = Depends(get_session),
    _actor: Actor = Depends(require_scope("admin")),
) -> ApiRequestDetail:
    r = await session.get(ApiRequest, request_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Request not found: {request_id}")
    return ApiRequestDetail.model_validate({**_request_read(r).model_dump(),
                                            "request_body": r.request_body, "response_body": r.response_body})


@router.get("/sources", response_model=SourcesResponse, summary="Who sent what, grouped")
async def sources(
    hours: int = Query(default=24, ge=1, le=24 * 90),
    session: AsyncSession = Depends(get_session),
    _actor: Actor = Depends(require_scope("read")),
) -> SourcesResponse:
    since = utc_now() - timedelta(hours=hours)
    classes = {f"{c}xx": func.sum(case(((ApiRequest.status >= c * 100) & (ApiRequest.status < c * 100 + 100), 1), else_=0))
               for c in (2, 3, 4, 5)}
    q = (select(ApiRequest.actor_name, ApiRequest.client_ip, ApiRequest.method, ApiRequest.route,
                func.count().label("total"), func.max(ApiRequest.ts).label("last"), *classes.values())
         .where(ApiRequest.ts >= since)
         .group_by(ApiRequest.actor_name, ApiRequest.client_ip, ApiRequest.method, ApiRequest.route)
         .order_by(func.count().desc()).limit(500))
    out = []
    for row in (await session.execute(q)).all():
        by_class = {k: int(v or 0) for k, v in zip(classes, row[6:], strict=True) if v}
        out.append(SourceRow(actor_name=row[0], client_ip=row[1], method=row[2], route=row[3],
                             total=row[4], by_class=by_class, last_seen=_as_utc_iso(row[5])))
    ignored = [IgnoredRow(rule_id=r.id, name=r.name, pattern=_pattern(r), hits=r.hits,
                          last_hit_at=_as_utc_iso(r.last_hit_at), last_ip=r.last_ip)
               for r in (await session.execute(select(ActivityRule).where(ActivityRule.action == "ignore")
                                               .order_by(ActivityRule.position))).scalars()]
    return SourcesResponse(hours=hours, sources=out, ignored=ignored)


def _pattern(r: ActivityRule) -> str:
    parts = [r.match_method or "*", r.match_path]
    if r.match_status:
        parts.append(r.match_status)
    if r.match_actor:
        parts.append(f"actor={r.match_actor}")
    if r.match_ip:
        parts.append(f"ip={r.match_ip}")
    return " ".join(parts)


# ── Attempts and events ────────────────────────────────────────────


def _attempt_read(a: DeliveryAttempt, with_bodies: bool) -> AttemptRead:
    exchange = a.exchange
    if exchange:
        # Rows written before URLs were stored host-only still hold the full
        # destination; never hand a path (possibly a credential) to a reader.
        exchange = [{**e, "url": e.get("url") if is_redacted_url_display(e.get("url")) else safe_url_display(e.get("url")),
                     "error": collapse_urls(e.get("error"))} for e in exchange]
    if exchange and not with_bodies:
        exchange = [{k: v for k, v in e.items() if k not in ("request_body", "response_body")} for e in exchange]
    return AttemptRead.model_validate({**{c: getattr(a, c) for c in AttemptRead.model_fields if hasattr(a, c)},
                                       "exchange": exchange})


@router.get("/attempts", response_model=Page[AttemptRead], summary="Attempts to hand messages to providers")
async def list_attempts(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    channel: str | None = None,
    notification_id: str | None = None,
    kind: str | None = Query(default=None, description="alert, escalation or test"),
    outcome: str | None = Query(default=None, description="sent, failed, deferred, permanent or timeout"),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[AttemptRead]:
    filters: list[Any] = []
    if channel:
        filters.append(DeliveryAttempt.channel == channel)
    if notification_id:
        filters.append(DeliveryAttempt.notification_id == notification_id)
    if kind:
        filters.append(DeliveryAttempt.kind == kind)
    if outcome:
        filters.append(DeliveryAttempt.outcome == outcome)
    total = (await session.execute(select(func.count()).select_from(DeliveryAttempt).where(*filters))).scalar_one()
    order = (DeliveryAttempt.started_at.asc(), DeliveryAttempt.id.asc()) if notification_id else \
        (DeliveryAttempt.started_at.desc(), DeliveryAttempt.id.desc())
    rows = (await session.execute(select(DeliveryAttempt).where(*filters).order_by(*order)
                                  .offset(skip).limit(limit))).scalars().all()
    bodies = actor.has_scope("admin")
    return Page(items=[_attempt_read(a, bodies) for a in rows], total=total, limit=limit, offset=skip)


@router.get("/events", response_model=Page[SystemEventRead], summary="State changes of inputs, rules and channels")
async def list_events(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    source_kind: str | None = Query(default=None, description="input, rule or channel"),
    source_name: str | None = None,
    event: str | None = None,
    session: AsyncSession = Depends(get_session),
    _actor: Actor = Depends(require_scope("read")),
) -> Page[SystemEventRead]:
    filters: list[Any] = []
    if source_kind:
        filters.append(SystemEvent.source_kind == source_kind)
    if source_name:
        filters.append(SystemEvent.source_name == source_name)
    if event:
        filters.append(SystemEvent.event == event)
    total = (await session.execute(select(func.count()).select_from(SystemEvent).where(*filters))).scalar_one()
    rows = (await session.execute(select(SystemEvent).where(*filters)
                                  .order_by(SystemEvent.ts.desc(), SystemEvent.id.desc()).offset(skip).limit(limit))).scalars().all()
    return Page(items=[SystemEventRead.model_validate(r) for r in rows], total=total, limit=limit, offset=skip)


# ── Rules ──────────────────────────────────────────────────────────


@router.get("/rules", response_model=list[ActivityRuleRead], summary="What the request log keeps (first match wins)")
async def list_rules(
    session: AsyncSession = Depends(get_session),
    _actor: Actor = Depends(require_scope("read")),
) -> list[ActivityRuleRead]:
    rows = (await session.execute(select(ActivityRule).order_by(ActivityRule.position, ActivityRule.id))).scalars().all()
    return [ActivityRuleRead.model_validate(r) for r in rows]


async def _changed(session: AsyncSession, actor: Actor, action: str, rule: ActivityRule, before: dict[str, Any] | None) -> None:
    await record_change(session, actor, action, resource_kind="activity_rule", resource_id=str(rule.id),
                        before=before, after=model_to_dict(rule) if action != "activity_rule.delete" else None)
    await session.commit()
    get_rule_cache().invalidate()


@router.post("/rules", response_model=ActivityRuleRead, status_code=status.HTTP_201_CREATED, summary="Add a rule")
async def create_rule(
    body: ActivityRuleCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> ActivityRuleRead:
    rule = ActivityRule(**body.model_dump())
    session.add(rule)
    await session.flush()
    await _changed(session, actor, "activity_rule.create", rule, None)
    await session.refresh(rule)
    return ActivityRuleRead.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=ActivityRuleRead, summary="Change a rule")
async def update_rule(
    rule_id: int,
    body: ActivityRuleUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> ActivityRuleRead:
    rule = await session.get(ActivityRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Rule not found: {rule_id}")
    before = model_to_dict(rule)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    await session.flush()
    await _changed(session, actor, "activity_rule.update", rule, before)
    await session.refresh(rule)
    return ActivityRuleRead.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a rule")
async def delete_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> None:
    rule = await session.get(ActivityRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Rule not found: {rule_id}")
    before = model_to_dict(rule)
    await session.delete(rule)
    await _changed(session, actor, "activity_rule.delete", rule, before)


@router.post("/rules/preview", response_model=RulePreview,
             summary="How many recent requests a rule would match")
async def preview_rule(
    body: ActivityRuleCreate,
    hours: int = Query(default=24, ge=1, le=24 * 30),
    session: AsyncSession = Depends(get_session),
    _actor: Actor = Depends(require_scope("read")),
) -> RulePreview:
    rule = Rule(0, body.name, body.match_method, body.match_path, body.match_status, body.match_actor,
                body.match_ip, body.action, body.keep_days, body.request_body, body.response_body)
    rows = (await session.execute(select(ApiRequest).where(ApiRequest.ts >= utc_now() - timedelta(hours=hours))
                                  .order_by(ApiRequest.ts.desc()).limit(5000))).scalars().all()
    hits = [r for r in rows if rule.matches(method=r.method, path=r.path.split("?", 1)[0], status=r.status,
                                           actor=r.actor_name, ip=r.client_ip)]
    return RulePreview(window_hours=hours, checked=len(rows), matched=len(hits),
                       examples=[_request_read(r) for r in hits[:5]])
