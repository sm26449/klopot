from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.page_api_request_read import PageApiRequestRead
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    method: None | str | Unset = UNSET,
    route: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    actor: None | str | Unset = UNSET,
    ip: None | str | Unset = UNSET,
    trace_id: None | str | Unset = UNSET,
    webhooks: bool | Unset = False,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_method: None | str | Unset
    if isinstance(method, Unset):
        json_method = UNSET
    else:
        json_method = method
    params["method"] = json_method

    json_route: None | str | Unset
    if isinstance(route, Unset):
        json_route = UNSET
    else:
        json_route = route
    params["route"] = json_route

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    else:
        json_status = status
    params["status"] = json_status

    json_actor: None | str | Unset
    if isinstance(actor, Unset):
        json_actor = UNSET
    else:
        json_actor = actor
    params["actor"] = json_actor

    json_ip: None | str | Unset
    if isinstance(ip, Unset):
        json_ip = UNSET
    else:
        json_ip = ip
    params["ip"] = json_ip

    json_trace_id: None | str | Unset
    if isinstance(trace_id, Unset):
        json_trace_id = UNSET
    else:
        json_trace_id = trace_id
    params["trace_id"] = json_trace_id

    params["webhooks"] = webhooks

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
        "url": "/v1/activity/requests",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageApiRequestRead | None:
    if response.status_code == 200:
        response_200 = PageApiRequestRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageApiRequestRead]:
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
    method: None | str | Unset = UNSET,
    route: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    actor: None | str | Unset = UNSET,
    ip: None | str | Unset = UNSET,
    trace_id: None | str | Unset = UNSET,
    webhooks: bool | Unset = False,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,

) -> Response[HTTPValidationError | PageApiRequestRead]:
    """ Requests Klopot received

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        method (None | str | Unset):
        route (None | str | Unset): Exact route template, e.g. /v1/fire
        search (None | str | Unset): Substring of the path
        status (None | str | Unset): 2xx, 4xx… or a code
        actor (None | str | Unset):
        ip (None | str | Unset):
        trace_id (None | str | Unset):
        webhooks (bool | Unset): Only inbound webhook / Alertmanager / SMS-inbox requests Default:
            False.
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageApiRequestRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
method=method,
route=route,
search=search,
status=status,
actor=actor,
ip=ip,
trace_id=trace_id,
webhooks=webhooks,
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
    method: None | str | Unset = UNSET,
    route: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    actor: None | str | Unset = UNSET,
    ip: None | str | Unset = UNSET,
    trace_id: None | str | Unset = UNSET,
    webhooks: bool | Unset = False,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,

) -> HTTPValidationError | PageApiRequestRead | None:
    """ Requests Klopot received

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        method (None | str | Unset):
        route (None | str | Unset): Exact route template, e.g. /v1/fire
        search (None | str | Unset): Substring of the path
        status (None | str | Unset): 2xx, 4xx… or a code
        actor (None | str | Unset):
        ip (None | str | Unset):
        trace_id (None | str | Unset):
        webhooks (bool | Unset): Only inbound webhook / Alertmanager / SMS-inbox requests Default:
            False.
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageApiRequestRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
method=method,
route=route,
search=search,
status=status,
actor=actor,
ip=ip,
trace_id=trace_id,
webhooks=webhooks,
from_=from_,
to=to,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    method: None | str | Unset = UNSET,
    route: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    actor: None | str | Unset = UNSET,
    ip: None | str | Unset = UNSET,
    trace_id: None | str | Unset = UNSET,
    webhooks: bool | Unset = False,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,

) -> Response[HTTPValidationError | PageApiRequestRead]:
    """ Requests Klopot received

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        method (None | str | Unset):
        route (None | str | Unset): Exact route template, e.g. /v1/fire
        search (None | str | Unset): Substring of the path
        status (None | str | Unset): 2xx, 4xx… or a code
        actor (None | str | Unset):
        ip (None | str | Unset):
        trace_id (None | str | Unset):
        webhooks (bool | Unset): Only inbound webhook / Alertmanager / SMS-inbox requests Default:
            False.
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageApiRequestRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
method=method,
route=route,
search=search,
status=status,
actor=actor,
ip=ip,
trace_id=trace_id,
webhooks=webhooks,
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
    method: None | str | Unset = UNSET,
    route: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    actor: None | str | Unset = UNSET,
    ip: None | str | Unset = UNSET,
    trace_id: None | str | Unset = UNSET,
    webhooks: bool | Unset = False,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,

) -> HTTPValidationError | PageApiRequestRead | None:
    """ Requests Klopot received

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        method (None | str | Unset):
        route (None | str | Unset): Exact route template, e.g. /v1/fire
        search (None | str | Unset): Substring of the path
        status (None | str | Unset): 2xx, 4xx… or a code
        actor (None | str | Unset):
        ip (None | str | Unset):
        trace_id (None | str | Unset):
        webhooks (bool | Unset): Only inbound webhook / Alertmanager / SMS-inbox requests Default:
            False.
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageApiRequestRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
method=method,
route=route,
search=search,
status=status,
actor=actor,
ip=ip,
trace_id=trace_id,
webhooks=webhooks,
from_=from_,
to=to,

    )).parsed
