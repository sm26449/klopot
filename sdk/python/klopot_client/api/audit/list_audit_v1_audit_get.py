from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.page_audit_log_read import PageAuditLogRead
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    action: None | str | Unset = UNSET,
    resource_kind: None | str | Unset = UNSET,
    resource_id: None | str | Unset = UNSET,
    actor_name: None | str | Unset = UNSET,
    trace_id: None | str | Unset = UNSET,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_action: None | str | Unset
    if isinstance(action, Unset):
        json_action = UNSET
    else:
        json_action = action
    params["action"] = json_action

    json_resource_kind: None | str | Unset
    if isinstance(resource_kind, Unset):
        json_resource_kind = UNSET
    else:
        json_resource_kind = resource_kind
    params["resource_kind"] = json_resource_kind

    json_resource_id: None | str | Unset
    if isinstance(resource_id, Unset):
        json_resource_id = UNSET
    else:
        json_resource_id = resource_id
    params["resource_id"] = json_resource_id

    json_actor_name: None | str | Unset
    if isinstance(actor_name, Unset):
        json_actor_name = UNSET
    else:
        json_actor_name = actor_name
    params["actor_name"] = json_actor_name

    json_trace_id: None | str | Unset
    if isinstance(trace_id, Unset):
        json_trace_id = UNSET
    else:
        json_trace_id = trace_id
    params["trace_id"] = json_trace_id

    json_from_: None | str | Unset
    if isinstance(from_, Unset):
        json_from_ = UNSET
    elif isinstance(from_, datetime.datetime):
        json_from_ = from_.isoformat()
    else:
        json_from_ = from_
    params["from"] = json_from_

    json_to: None | str | Unset
    if isinstance(to, Unset):
        json_to = UNSET
    elif isinstance(to, datetime.datetime):
        json_to = to.isoformat()
    else:
        json_to = to
    params["to"] = json_to


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/audit",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageAuditLogRead | None:
    if response.status_code == 200:
        response_200 = PageAuditLogRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageAuditLogRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    action: None | str | Unset = UNSET,
    resource_kind: None | str | Unset = UNSET,
    resource_id: None | str | Unset = UNSET,
    actor_name: None | str | Unset = UNSET,
    trace_id: None | str | Unset = UNSET,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,

) -> Response[HTTPValidationError | PageAuditLogRead]:
    """ Query admin action audit log

     Paged audit-log query. Filters: action (e.g. 'rule.update'), resource_kind (rule / template /
    channel / variable / etc.), resource_id, actor_name, trace_id, time range (from/to ISO8601). Ordered
    by ts DESC (most recent first).

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        action (None | str | Unset):
        resource_kind (None | str | Unset):
        resource_id (None | str | Unset):
        actor_name (None | str | Unset):
        trace_id (None | str | Unset):
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageAuditLogRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
action=action,
resource_kind=resource_kind,
resource_id=resource_id,
actor_name=actor_name,
trace_id=trace_id,
from_=from_,
to=to,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    action: None | str | Unset = UNSET,
    resource_kind: None | str | Unset = UNSET,
    resource_id: None | str | Unset = UNSET,
    actor_name: None | str | Unset = UNSET,
    trace_id: None | str | Unset = UNSET,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,

) -> HTTPValidationError | PageAuditLogRead | None:
    """ Query admin action audit log

     Paged audit-log query. Filters: action (e.g. 'rule.update'), resource_kind (rule / template /
    channel / variable / etc.), resource_id, actor_name, trace_id, time range (from/to ISO8601). Ordered
    by ts DESC (most recent first).

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        action (None | str | Unset):
        resource_kind (None | str | Unset):
        resource_id (None | str | Unset):
        actor_name (None | str | Unset):
        trace_id (None | str | Unset):
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageAuditLogRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
action=action,
resource_kind=resource_kind,
resource_id=resource_id,
actor_name=actor_name,
trace_id=trace_id,
from_=from_,
to=to,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    action: None | str | Unset = UNSET,
    resource_kind: None | str | Unset = UNSET,
    resource_id: None | str | Unset = UNSET,
    actor_name: None | str | Unset = UNSET,
    trace_id: None | str | Unset = UNSET,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,

) -> Response[HTTPValidationError | PageAuditLogRead]:
    """ Query admin action audit log

     Paged audit-log query. Filters: action (e.g. 'rule.update'), resource_kind (rule / template /
    channel / variable / etc.), resource_id, actor_name, trace_id, time range (from/to ISO8601). Ordered
    by ts DESC (most recent first).

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        action (None | str | Unset):
        resource_kind (None | str | Unset):
        resource_id (None | str | Unset):
        actor_name (None | str | Unset):
        trace_id (None | str | Unset):
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageAuditLogRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
action=action,
resource_kind=resource_kind,
resource_id=resource_id,
actor_name=actor_name,
trace_id=trace_id,
from_=from_,
to=to,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    action: None | str | Unset = UNSET,
    resource_kind: None | str | Unset = UNSET,
    resource_id: None | str | Unset = UNSET,
    actor_name: None | str | Unset = UNSET,
    trace_id: None | str | Unset = UNSET,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,

) -> HTTPValidationError | PageAuditLogRead | None:
    """ Query admin action audit log

     Paged audit-log query. Filters: action (e.g. 'rule.update'), resource_kind (rule / template /
    channel / variable / etc.), resource_id, actor_name, trace_id, time range (from/to ISO8601). Ordered
    by ts DESC (most recent first).

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        action (None | str | Unset):
        resource_kind (None | str | Unset):
        resource_id (None | str | Unset):
        actor_name (None | str | Unset):
        trace_id (None | str | Unset):
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageAuditLogRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
action=action,
resource_kind=resource_kind,
resource_id=resource_id,
actor_name=actor_name,
trace_id=trace_id,
from_=from_,
to=to,

    )).parsed
