from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.input_kind import InputKind
from ...models.page_input_read import PageInputRead
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    kind: InputKind | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_kind: None | str | Unset
    if isinstance(kind, Unset):
        json_kind = UNSET
    elif isinstance(kind, InputKind):
        json_kind = kind.value
    else:
        json_kind = kind
    params["kind"] = json_kind

    json_enabled: bool | None | Unset
    if isinstance(enabled, Unset):
        json_enabled = UNSET
    else:
        json_enabled = enabled
    params["enabled"] = json_enabled


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/inputs",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageInputRead | None:
    if response.status_code == 200:
        response_200 = PageInputRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageInputRead]:
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
    kind: InputKind | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,

) -> Response[HTTPValidationError | PageInputRead]:
    """ List inputs

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        kind (InputKind | None | Unset):
        enabled (bool | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageInputRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
kind=kind,
enabled=enabled,

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
    kind: InputKind | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,

) -> HTTPValidationError | PageInputRead | None:
    """ List inputs

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        kind (InputKind | None | Unset):
        enabled (bool | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageInputRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
kind=kind,
enabled=enabled,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    kind: InputKind | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,

) -> Response[HTTPValidationError | PageInputRead]:
    """ List inputs

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        kind (InputKind | None | Unset):
        enabled (bool | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageInputRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
kind=kind,
enabled=enabled,

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
    kind: InputKind | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,

) -> HTTPValidationError | PageInputRead | None:
    """ List inputs

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        kind (InputKind | None | Unset):
        enabled (bool | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageInputRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
kind=kind,
enabled=enabled,

    )).parsed
