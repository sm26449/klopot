"""``/v1/inputs`` — input source CRUD + health probe + webhook receiver.

After every mutation, the input manager reloads (hot swap of
adapters + topic filters)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import model_to_dict, record_change
from ...auth import Actor, client_address, require_scope
from ...config import get_settings
from ...core.manager import get_manager
from ...db import get_session
from ...db.models import Input, Variable
from ...inputs.webhook import INBOUND_KINDS, WebhookInput, validate_inbound_auth, webhook_auth_ok
from ...schemas.common import InputKind, Page
from ...schemas.input import InputCreate, InputHealth, InputRead, InputUpdate
from ...secrets_registry import mask_config, merge_secret_update, secret_status
from ...utils.failure_budget import FailureBudget
from ._crud import crud_get_or_404, crud_list, enforce_create_cap, flush_or_409

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_supported_kind(kind: Any) -> None:
    """Reject an input kind that has no registered runtime adapter (e.g.
    schedule / email_imap) — the enum lists them but nothing implements
    them, so accepting one yields a dead input (audit F29)."""
    from ...inputs import REGISTRY

    k = getattr(kind, "value", kind)
    if k not in REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"input kind {k!r} is not supported (no adapter). "
                f"Supported kinds: {sorted(REGISTRY)}"
            ),
        )


def _require_valid_auth(kind: Any, config: dict[str, Any] | None) -> None:
    """An inbound input must be able to authenticate as configured
    (inputs/webhook.py ``validate_inbound_auth``): 422 otherwise."""
    if getattr(kind, "value", kind) not in INBOUND_KINDS:
        return
    try:
        validate_inbound_auth(config or {})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from None


def _to_read(obj: Input) -> InputRead:
    """Serialize with literal secrets masked (audit 2026-11-07 C-1/C-2).

    The MQTT broker password used to be returned verbatim to any
    ``read``-scoped key; every read path now goes through here.
    """
    out = InputRead.model_validate(obj)
    out.config = mask_config("input", obj.kind, obj.config)
    out.secret_fields_set = secret_status("input", obj.kind, obj.config)
    return out


@router.get("", response_model=Page[InputRead], summary="List inputs")
async def list_inputs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    kind: InputKind | None = None,
    enabled: bool | None = None,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> Page[InputRead]:
    filters = []
    if kind is not None:
        filters.append(Input.kind == kind)
    if enabled is not None:
        filters.append(Input.enabled.is_(enabled))
    items, total = await crud_list(
        session, Input, skip=skip, limit=limit, filters=filters,
        order_by=Input.name,
    )
    return Page(
        items=[_to_read(i) for i in items],
        total=total, limit=limit, offset=skip,
    )


@router.post(
    "", response_model=InputRead, status_code=status.HTTP_201_CREATED,
    summary="Create input",
)
async def create_input(
    body: InputCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> InputRead:
    _require_supported_kind(body.kind)
    _require_valid_auth(body.kind, body.config)
    await enforce_create_cap(session, Input, get_settings().max_inputs, entity="Input")
    obj = Input(**body.model_dump())
    session.add(obj)
    await flush_or_409(session, "Input create")
    await session.refresh(obj)
    await record_change(
        session, actor, "input.create",
        resource_kind="input", resource_id=str(obj.id),
        after=model_to_dict(obj),
    )
    await session.commit()
    # Hot reload — manager re-reads DB and starts the new adapter
    await get_manager().reload()
    return _to_read(obj)


@router.get("/{input_id}", response_model=InputRead, summary="Get input")
async def get_input(
    input_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> InputRead:
    obj = await crud_get_or_404(session, Input, input_id)
    return _to_read(obj)


@router.patch("/{input_id}", response_model=InputRead, summary="Update input")
async def update_input(
    input_id: int,
    body: InputUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> InputRead:
    obj = await crud_get_or_404(session, Input, input_id)
    if body.kind is not None:
        _require_supported_kind(body.kind)
    before = model_to_dict(obj)
    patch = body.model_dump(exclude_unset=True)
    if "config" in patch and patch["config"] is not None:
        # Secret fields omitted / null / masked-echo keep their stored
        # value; "" clears; anything else replaces (secrets_registry).
        kind = patch.get("kind") or obj.kind
        patch["config"] = merge_secret_update("input", kind, obj.config, patch["config"])
    # Judge the result (merged secrets, the kind it ends up with).
    _require_valid_auth(patch.get("kind") or obj.kind,
                        patch["config"] if patch.get("config") is not None else obj.config)
    for k, v in patch.items():
        setattr(obj, k, v)
    await flush_or_409(session, "Input update")
    await session.refresh(obj)
    await record_change(
        session, actor, "input.update",
        resource_kind="input", resource_id=str(obj.id),
        before=before, after=model_to_dict(obj),
    )
    await session.commit()
    await get_manager().reload()
    return _to_read(obj)


async def _bound_variable_names(session: AsyncSession, input_id: int) -> list[str]:
    """Names of variables currently bound to ``input_id`` (audit B-01/F11)."""
    return list(
        (
            await session.execute(
                select(Variable.name).where(Variable.input_id == input_id)
            )
        ).scalars().all()
    )


def _input_in_use(names: list[str]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "INPUT_IN_USE",
            "message": f"Input is bound by {len(names)} variable(s); "
                       "rebind or delete those variables first.",
            "variables": names,
        },
    )


@router.delete("/{input_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete input")
async def delete_input(
    input_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
):
    obj = await crud_get_or_404(session, Input, input_id)
    # Refuse while variables still reference this input (audit F11): a null
    # input_id means "accept any source", so deleting here would silently
    # *widen* a bound variable's trust to every broker. Make the operator
    # unbind/retarget first (as channels do). The pre-check gives an
    # informative 409; the ON DELETE RESTRICT FK is the authoritative guard
    # that also closes the check-then-commit race with a concurrent insert
    # (audit B-01), surfaced as the same 409 on commit.
    bound = await _bound_variable_names(session, input_id)
    if bound:
        raise _input_in_use(bound)
    before = model_to_dict(obj)
    await session.delete(obj)
    await record_change(
        session, actor, "input.delete",
        resource_kind="input", resource_id=str(input_id), before=before,
    )
    try:
        await session.commit()
    except IntegrityError as e:
        # A variable was bound to this input after our pre-check and before
        # our commit; RESTRICT refused the delete at the DB boundary. Report
        # the same conflict rather than leaking a raw FK error (audit B-01).
        await session.rollback()
        raise _input_in_use(await _bound_variable_names(session, input_id)) from e
    await get_manager().reload()


@router.get("/{input_id}/health", response_model=InputHealth, summary="Adapter health probe")
async def input_health(
    input_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("read")),
) -> InputHealth:
    obj = await crud_get_or_404(session, Input, input_id)
    h = get_manager().adapter_health().get(obj.name) or {}
    return InputHealth(
        name=obj.name,
        kind=obj.kind,
        connected=bool(h.get("connected", False)),
        last_msg_ts=h.get("last_msg_ts"),
        msg_count=int(h.get("msg_count") or 0),
        error=h.get("error"),
    )


@router.post("/{input_id}/restart", summary="Force restart of an adapter")
async def restart_input(
    input_id: int,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_scope("admin")),
) -> dict[str, str]:
    obj = await crud_get_or_404(session, Input, input_id)
    # A plain reload keeps an adapter whose config is unchanged, so a
    # crashed/stopped adapter would not actually restart. Force a real
    # stop + reconstruct of this named adapter (audit F13).
    rebuilt = await get_manager().force_restart(obj.name)
    await record_change(
        session, actor, "input.restart",
        resource_kind="input", resource_id=str(obj.id),
        after={"name": obj.name, "rebuilt": rebuilt},
    )
    await session.commit()
    return {
        "status": "restarted" if rebuilt else "not_running",
        "name": obj.name,
    }


# ── Webhook receiver (no API key — auth is per-input via X-Input-Token) ──

# Wrong or missing input tokens (and ids that are no input), per address:
# kept apart from the API-key budget, so a sender with a stale token does not
# lock out the keys used from the same address.
_TOKEN_BUDGET = FailureBudget(max_failures=5, window_sec=60.0, max_addresses=10_000)


def reset_input_token_failures() -> None:
    """Forget every wrong-token count (tests)."""
    _TOKEN_BUDGET.reset()


def _presented_token(kind: str, x_input_token: str | None, authorization: str | None) -> str | None:
    """The token as sent: X-Input-Token, or for Alertmanager / Grafana
    ``Authorization: Bearer <token>`` (their http_config.authorization)."""
    if x_input_token is not None or kind != "alertmanager" or not authorization:
        return x_input_token
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else None


@router.post(
    "/{input_id}/webhook",
    summary="Receive a webhook payload for this input",
    description=(
        "Public endpoint where external systems POST values. The "
        "input declares whether auth is required and which env var "
        "holds the expected token. Bypasses the normal X-API-Key "
        "auth so external services can post without a full alertd "
        "credential — they only need the per-input token."
    ),
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_webhook(
    input_id: int,
    request: Request,
    x_input_token: str | None = Header(default=None, alias="X-Input-Token"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # Anonymous endpoint: nothing about an input — whether the id exists, its
    # kind or state — is said before the caller's token is accepted (reviews
    # K10, F11). An id that is no inbound input, a disabled input and a wrong
    # or missing token all get the same 401, and all count against the
    # address's budget; the input's editor lists them (recent requests).
    ip = client_address(request)
    if _TOKEN_BUDGET.spent(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many refused input requests from this address",
            headers={"Retry-After": str(_TOKEN_BUDGET.retry_after)},
        )
    obj = await session.get(Input, input_id)
    if (obj is None or not obj.enabled or obj.kind.value not in INBOUND_KINDS
            or not webhook_auth_ok(obj.config or {}, _presented_token(obj.kind.value, x_input_token, authorization))):
        _TOKEN_BUDGET.note(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown input or wrong token",
            headers={"WWW-Authenticate": 'Bearer realm="klopot-input"'},
        )
    # The caller got in: the activity log may keep this request's body.
    request.state.inbound_ok = True

    adapter = get_manager().get_adapter(obj.name)
    if adapter is None or not isinstance(adapter, WebhookInput):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Adapter for input {obj.name} not running — try POST /restart first",
        )

    # Decode body — try JSON first, fall back to text. A tighter cap than the
    # global request limit applies to this public, token-gated endpoint
    # (audit A-08): webhook values are small, so refuse an outsized body before
    # decoding/parsing it.
    body_bytes = await request.body()
    if obj.kind.value == "alertmanager":
        return await _receive_alertmanager(session, obj, body_bytes)
    max_webhook = get_settings().max_webhook_bytes
    if len(body_bytes) > max_webhook:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Webhook body exceeds {max_webhook} bytes",
        )
    payload: Any
    try:
        import json as _json

        payload = _json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except (ValueError, UnicodeDecodeError):
        payload = body_bytes.decode("utf-8", errors="replace")

    try:
        await adapter.deliver(payload)
    except Exception as e:
        logger.exception("Webhook delivery failed for %s", obj.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"delivery error: {type(e).__name__}",
        ) from e

    return {"status": "accepted", "input": obj.name}


async def _receive_alertmanager(session: AsyncSession, obj: Input, body_bytes: bytes) -> dict[str, Any]:
    """Alertmanager / Grafana group → external episodes (app/services/alertmanager.py)."""
    import json as _json

    from ...services import alertmanager as am_service

    limit = get_settings().max_alertmanager_bytes
    if len(body_bytes) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Alertmanager body exceeds {limit} bytes",
        )
    try:
        payload = _json.loads(body_bytes.decode("utf-8")) if body_bytes else None
    except (ValueError, UnicodeDecodeError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="body must be JSON") from e
    summary = await am_service.ingest(session, obj, payload)
    if summary["errors"] and not summary["alerts"]:
        await session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=summary["errors"][0])
    await session.commit()
    return {"status": "accepted", "input": obj.name, **summary}
