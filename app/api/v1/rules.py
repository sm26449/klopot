"""``/v1/rules`` — rule CRUD + test/eval-now actions."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ...audit import model_to_dict, record_change
from ...auth import Actor, require_scope
from ...config import get_settings
from ...core import dispatcher as dispatcher_module
from ...core import eval as eval_module
from ...core.engine import get_engine, rule_context, settings_evaluator
from ...core.eval import MISSING_INPUT_PREFIX
from ...core.incidents import lifecycle_config
from ...core.rule_state_ops import reset_streak_on_reconfig
from ...core.state_cache import get_state_cache
from ...db import get_session
from ...db.models import Rule, RuleState, RuleTransition, Template
from ...schemas.common import Page
from ...schemas.fire import FireResponse
from ...schemas.rule import (
    EvalStatus,
    RuleBulkEnabled,
    RuleBulkResult,
    RuleCreate,
    RuleRead,
    RuleTransitionRead,
    RuleUpdate,
)
from ...utils.like import like_escape
from ._crud import crud_get_or_404, crud_list, enforce_create_cap, flush_or_409

router = APIRouter()


def _status_clause(status_: EvalStatus) -> ColumnElement[bool]:
    """SQL twin of ``schemas.rule.eval_status_of``."""
    waiting = Rule.last_eval_error.like(f"{MISSING_INPUT_PREFIX}%")
    if status_ == "error":
        return or_(
            Rule.consecutive_eval_errors > 0,
            and_(Rule.last_eval_error.is_not(None), not_(waiting)),
        )
    clean = Rule.consecutive_eval_errors == 0
    if status_ == "no_data":
        return and_(clean, waiting)
    return and_(clean, Rule.last_eval_error.is_(None))

# Wall-clock budget for a single /rules/validate evaluation (audit R08).
_VALIDATE_EVAL_BUDGET_SEC = 2.0


class TestRuleBody(BaseModel):
    """``POST /v1/rules/{id}/test`` body — supply mock context."""

    context: dict[str, Any] = Field(default_factory=dict)


class EvalRuleResult(BaseModel):
    """``POST /v1/rules/{id}/eval-now`` response."""

    matched: bool
    error: str | None = None
    missing_vars: list[str] | None = None
    context: dict[str, Any]
    consecutive_match_count: int


class ValidateRuleBody(BaseModel):
    """``POST /v1/rules/validate`` body."""

    # Bounded so a read-scoped caller can't submit a huge expression that
    # amplifies a pathological regex (audit R08).
    condition_expr: str = Field(min_length=1, max_length=2000)
    vars_extract: list[str] | None = None
    # "What if": values laid over the live ones for this evaluation only
    # (review RL-31) — e.g. {"battery.soc": 12}; null = the input is missing.
    # var_age / fresh / has and the clock still read the live state.
    context: dict[str, Any] | None = Field(default=None, max_length=200)

    @field_validator("context")
    @classmethod
    def _bounded_context(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and len(json.dumps(v, default=str)) > _MAX_CONTEXT_BYTES:
            raise ValueError(f"context too large (> {_MAX_CONTEXT_BYTES} bytes)")
        return v


_MAX_CONTEXT_BYTES = 65536


class ReferencedVar(BaseModel):
    name: str
    live_value: Any = None
    age_sec: float | None = None
    is_stale: bool = False
    present: bool = True


class ValidateRuleResult(BaseModel):
    ok: bool
    error: str | None = None
    result: Any = None
    referenced_vars: list[ReferencedVar] = Field(default_factory=list)
    unknown_vars: list[str] = Field(default_factory=list)


def _validate_expr_or_422(expr: str) -> None:
    """Refuse an expression outside the language contract at write time, so a
    dangerous one is never stored (audit A-01)."""
    try:
        eval_module.validate_expression(expr)
    except eval_module.ExpressionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid expression: {e}",
        ) from e


@router.get("", response_model=Page[RuleRead], summary="List rules")
async def list_rules(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    template_type: str | None = None,
    enabled: bool | None = None,
    has_error: bool | None = Query(
        default=None,
        description="true → only rules whose expression fails (eval_status=error); "
        "false → the rest. A rule waiting for an input is eval_status=no_data.",
    ),
    eval_status: EvalStatus | None = Query(
        default=None, description="ok | no_data (waiting for an input) | error (expression fails).",
    ),
    category: str | None = Query(
        default=None,
        description="Category of the rule's template (case-insensitive); '__none__' = uncategorized.",
    ),
    never_fired: bool | None = Query(
        default=None, description="true → rules that have never fired; false → rules that have.",
    ),
    search: str | None = Query(
        default=None, description="Free-text match on name / condition / summary.",
    ),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[RuleRead]:
    filters = []
    if template_type is not None:
        filters.append(Rule.template_type == template_type)
    if enabled is not None:
        filters.append(Rule.enabled.is_(enabled))
    if has_error is True:
        eval_status = eval_status or "error"
    elif has_error is False:
        filters.append(not_(_status_clause("error")))
    if eval_status is not None:
        filters.append(_status_clause(eval_status))
    if category is not None:
        categorised = select(Template.type).where(Template.category.is_not(None))
        if category == "__none__":
            filters.append(Rule.template_type.not_in(categorised))
        else:
            filters.append(Rule.template_type.in_(
                select(Template.type).where(func.lower(Template.category) == category.lower())
            ))
    if never_fired is True:
        filters.append(Rule.last_fired_at.is_(None))
    elif never_fired is False:
        filters.append(Rule.last_fired_at.is_not(None))
    if search:
        like = f"%{like_escape(search)}%"
        filters.append(or_(
            Rule.name.like(like, escape="\\"),
            Rule.condition_expr.like(like, escape="\\"),
            Rule.trigger_summary.like(like, escape="\\"),
        ))
    items, total = await crud_list(
        session, Rule, skip=skip, limit=limit, filters=filters,
        order_by=(Rule.sort_order.asc(), Rule.name.asc()),
    )
    return Page(
        items=[RuleRead.model_validate(i) for i in items],
        total=total, limit=limit, offset=skip,
    )


@router.post(
    "", response_model=RuleRead, status_code=status.HTTP_201_CREATED,
    summary="Create rule",
)
async def create_rule(
    body: RuleCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> RuleRead:
    _validate_expr_or_422(body.condition_expr)
    if body.recovery_expr:
        _validate_expr_or_422(body.recovery_expr)
    await enforce_create_cap(session, Rule, get_settings().max_rules, entity="Rule")
    obj = Rule(**body.model_dump())
    session.add(obj)
    await flush_or_409(session, "Rule create")
    await session.refresh(obj)
    await record_change(
        session, actor, "rule.create",
        resource_kind="rule", resource_id=str(obj.id),
        after=model_to_dict(obj),
    )
    await session.commit()
    await get_engine().reload_rules()
    return RuleRead.model_validate(obj)


@router.get(
    "/by-name/{name}",
    response_model=RuleRead,
    summary="Get rule by name",
    description=(
        "Companion to ``GET /v1/rules/{rule_id}`` for callers that hold the "
        "rule name (config files, log analysis, UI URL routing) but not the "
        "auto-increment id. Mounted under ``/by-name/`` so it never collides "
        "with the integer-id route."
    ),
)
async def get_rule_by_name(
    name: str,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> RuleRead:
    from sqlalchemy import select
    obj = (
        await session.execute(select(Rule).where(Rule.name == name))
    ).scalar_one_or_none()
    if obj is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule not found: {name}",
        )
    return RuleRead.model_validate(obj)


@router.get("/{rule_id}", response_model=RuleRead, summary="Get rule")
async def get_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> RuleRead:
    obj = await crud_get_or_404(session, Rule, rule_id)
    return RuleRead.model_validate(obj)


@router.get(
    "/{rule_id}/transitions",
    response_model=list[RuleTransitionRead],
    summary="Run-state history of a rule, newest first",
    description=(
        "One entry per change of the rule's run state (inactive, pending, firing, "
        "no_data, error), never per evaluation. Kept as long as the log "
        "(ALERTD_LOG_RETENTION_DAYS); a flapping rule records at most 60 changes "
        "an hour, and the next entry's detail says how many were skipped."
    ),
)
async def rule_transitions(
    rule_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> list[RuleTransitionRead]:
    await crud_get_or_404(session, Rule, rule_id)
    rows = (await session.execute(
        select(RuleTransition).where(RuleTransition.rule_id == rule_id)
        .order_by(RuleTransition.id.desc()).limit(limit)
    )).scalars().all()
    return [RuleTransitionRead.model_validate(r) for r in rows]


@router.patch("/{rule_id}", response_model=RuleRead, summary="Update rule")
async def update_rule(
    rule_id: int,
    body: RuleUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> RuleRead:
    obj = (await session.execute(
        select(Rule).where(Rule.id == rule_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    before = model_to_dict(obj)
    prev_expr = obj.condition_expr
    prev_lifecycle = lifecycle_config(obj)
    fields = body.model_dump(exclude_unset=True)
    if "condition_expr" in fields:
        _validate_expr_or_422(fields["condition_expr"])
    if fields.get("recovery_expr"):
        _validate_expr_or_422(fields["recovery_expr"])
    for k, v in fields.items():
        setattr(obj, k, v)
    # Durably reset the match streak if the condition expression changed, in
    # this same transaction, so a restart can't restore a streak counted
    # against the old expression (audit B-06).
    await reset_streak_on_reconfig(
        session, obj, previous_condition_expr=prev_expr, previous_lifecycle=prev_lifecycle,
    )
    await flush_or_409(session, "Rule update")
    await session.refresh(obj)
    await record_change(
        session, actor, "rule.update",
        resource_kind="rule", resource_id=str(obj.id),
        before=before, after=model_to_dict(obj),
    )
    await session.commit()
    await get_engine().reload_rules()
    return RuleRead.model_validate(obj)


@router.post("/bulk/enabled", response_model=RuleBulkResult, summary="Enable or disable several rules")
async def bulk_set_enabled(
    body: RuleBulkEnabled,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> RuleBulkResult:
    """One transaction, one audit entry per changed rule, one engine reload —
    instead of a PATCH (and a reload) per rule from the admin UI's bulk bar."""
    ids = list(dict.fromkeys(body.ids))
    rows = (await session.execute(
        select(Rule).where(Rule.id.in_(ids)).with_for_update()
        .execution_options(populate_existing=True)
    )).scalars().all()
    found = {r.id: r for r in rows}
    result = RuleBulkResult(not_found=[i for i in ids if i not in found])
    for rule_id in ids:
        obj = found.get(rule_id)
        if obj is None:
            continue
        if obj.enabled == body.enabled:
            result.unchanged.append(rule_id)
            continue
        before = model_to_dict(obj)
        obj.enabled = body.enabled
        await session.flush()
        await record_change(
            session, actor, "rule.update",
            resource_kind="rule", resource_id=str(obj.id),
            before=before, after=model_to_dict(obj),
        )
        result.updated.append(rule_id)
    await session.commit()
    if result.updated:
        await get_engine().reload_rules()
    return result


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete rule")
async def delete_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
):
    obj = await crud_get_or_404(session, Rule, rule_id)
    before = model_to_dict(obj)
    await session.delete(obj)
    await record_change(
        session, actor, "rule.delete",
        resource_kind="rule", resource_id=str(rule_id), before=before,
    )
    await session.commit()
    await get_engine().reload_rules()


# ── Actions ────────────────────────────────────────────────────────


@router.post(
    "/{rule_id}/test",
    response_model=FireResponse,
    summary="Test fire — bypass throttle/quiet, dry-run on mock context",
    description=(
        "Fires the rule's template with caller-supplied context, as an "
        "administrator's test: marked as a test, and throttle, quiet hours "
        "and de-duplication are skipped (template.enabled and snooze still "
        "apply). Useful from the UI to preview a rendered title/message."
    ),
)
async def test_rule(
    rule_id: int,
    body: TestRuleBody,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> FireResponse:
    rule = await crud_get_or_404(session, Rule, rule_id)
    envelope = dispatcher_module.FireEnvelope(
        type=rule.template_type,
        context=dict(body.context),
        test=True,
        override_silencing=True,      # admin-only route
        source=f"test:{actor.name}",
        rule_id=rule.id,
    )
    result = await dispatcher_module.fire(envelope, session)
    await session.commit()
    return FireResponse(**result.as_dict())


@router.post(
    "/{rule_id}/eval-now",
    response_model=EvalRuleResult,
    summary="Force evaluate rule against current state cache (no fire)",
    description=(
        "Builds the rule's context from the live state cache, runs the "
        "condition expression once, and returns the outcome. Does NOT "
        "increment persist counters or dispatch — diagnostic only."
    ),
)
async def eval_now(
    rule_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> EvalRuleResult:
    rule = await crud_get_or_404(session, Rule, rule_id)
    cache = get_state_cache()
    # Exactly what the engine tick sees, staleness filtering included.
    ctx = rule_context(cache, rule.vars_extract, rule.condition_expr, rule.recovery_expr)

    res = eval_module.evaluate(rule.condition_expr, ctx, evaluator=settings_evaluator(cache))

    state = (
        await session.execute(
            select(RuleState).where(RuleState.rule_id == rule.id)
        )
    ).scalar_one_or_none()
    counter = state.consecutive_match_count if state else 0

    return EvalRuleResult(
        matched=bool(res.value) if res.ok else False,
        error=res.error,
        missing_vars=res.missing_vars,
        context=ctx,
        consecutive_match_count=counter,
    )


@router.post(
    "/validate",
    response_model=ValidateRuleResult,
    summary="Parse + check a condition expression (no rule, no side effects)",
    description=(
        "Evaluates the expression against the live state cache so the UI "
        "editor can show whether it parses, which variables it references "
        "(with their current value / age / staleness) and which names are "
        "unknown. Does not create or modify any rule."
    ),
)
async def validate_rule(
    body: ValidateRuleBody,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> ValidateRuleResult:
    cache = get_state_cache()
    snap = cache.snapshot()
    # The context the engine would build for a rule with this
    # ``vars_extract`` (review RL-02: it was ignored here).
    ctx = rule_context(cache, body.vars_extract, body.condition_expr)
    if body.context:
        ctx = {**ctx, **body.context}

    # User regexes compile under RE2 (audit V10), which matches in linear time,
    # so a catastrophic pattern can no longer block the loop. This off-thread
    # wall-clock budget stays as defense-in-depth for any other costly
    # expression, returning a clean 422 instead of hanging the request.
    try:
        res = await asyncio.wait_for(
            asyncio.to_thread(
                eval_module.evaluate,
                body.condition_expr, ctx, evaluator=settings_evaluator(cache),
            ),
            timeout=_VALIDATE_EVAL_BUDGET_SEC,
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="expression too expensive to evaluate (possible catastrophic regex)",
        ) from None

    referenced: list[ReferencedVar] = []
    unknown: list[str] = []
    for name in eval_module.display_names(body.condition_expr):
        vs = snap.get(name)
        if vs is None:
            unknown.append(name)
            referenced.append(ReferencedVar(name=name, present=False))
        else:
            referenced.append(ReferencedVar(
                name=name,
                live_value=vs.value,
                age_sec=round(vs.age_sec(), 3),
                is_stale=vs.is_stale(),
                present=True,
            ))

    return ValidateRuleResult(
        ok=res.ok,
        error=res.error,
        result=res.value if res.ok else None,
        referenced_vars=referenced,
        unknown_vars=unknown,
    )
