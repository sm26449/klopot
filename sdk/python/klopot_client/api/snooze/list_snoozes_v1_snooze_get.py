from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.page_snooze_read import PageSnoozeRead
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    scope: None | str | Unset = UNSET,
    target: None | str | Unset = UNSET,
    active: bool | Unset = True,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_scope: None | str | Unset
    if isinstance(scope, Unset):
        json_scope = UNSET
    else:
        json_scope = scope
    params["scope"] = json_scope

    json_target: None | str | Unset
    if isinstance(target, Unset):
        json_target = UNSET
    else:
        json_target = target
    params["target"] = json_target

    params["active"] = active


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/snooze",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageSnoozeRead | None:
    if response.status_code == 200:
        response_200 = PageSnoozeRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageSnoozeRead]:
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
    scope: None | str | Unset = UNSET,
    target: None | str | Unset = UNSET,
    active: bool | Unset = True,

) -> Response[HTTPValidationError | PageSnoozeRead]:
    """ List active or all snoozes

     Paged list. ``active=true`` (default) filters to entries whose ``until > now``. Filter by ``scope``
    (type/rule/channel) and ``target`` to drill down.

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        scope (None | str | Unset):
        target (None | str | Unset):
        active (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageSnoozeRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
scope=scope,
target=target,
active=active,

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
    scope: None | str | Unset = UNSET,
    target: None | str | Unset = UNSET,
    active: bool | Unset = True,

) -> HTTPValidationError | PageSnoozeRead | None:
    """ List active or all snoozes

     Paged list. ``active=true`` (default) filters to entries whose ``until > now``. Filter by ``scope``
    (type/rule/channel) and ``target`` to drill down.

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        scope (None | str | Unset):
        target (None | str | Unset):
        active (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageSnoozeRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
scope=scope,
target=target,
active=active,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    scope: None | str | Unset = UNSET,
    target: None | str | Unset = UNSET,
    active: bool | Unset = True,

) -> Response[HTTPValidationError | PageSnoozeRead]:
    """ List active or all snoozes

     Paged list. ``active=true`` (default) filters to entries whose ``until > now``. Filter by ``scope``
    (type/rule/channel) and ``target`` to drill down.

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        scope (None | str | Unset):
        target (None | str | Unset):
        active (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageSnoozeRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
scope=scope,
target=target,
active=active,

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
    scope: None | str | Unset = UNSET,
    target: None | str | Unset = UNSET,
    active: bool | Unset = True,

) -> HTTPValidationError | PageSnoozeRead | None:
    """ List active or all snoozes

     Paged list. ``active=true`` (default) filters to entries whose ``until > now``. Filter by ``scope``
    (type/rule/channel) and ``target`` to drill down.

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        scope (None | str | Unset):
        target (None | str | Unset):
        active (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageSnoozeRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
scope=scope,
target=target,
active=active,

    )).parsed
