from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.page_api_key_read import PageApiKeyRead
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    enabled: bool | None | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_enabled: bool | None | Unset
    if isinstance(enabled, Unset):
        json_enabled = UNSET
    else:
        json_enabled = enabled
    params["enabled"] = json_enabled


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/api_keys",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageApiKeyRead | None:
    if response.status_code == 200:
        response_200 = PageApiKeyRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageApiKeyRead]:
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
    enabled: bool | None | Unset = UNSET,

) -> Response[HTTPValidationError | PageApiKeyRead]:
    """ List API keys

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        enabled (bool | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageApiKeyRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
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
    enabled: bool | None | Unset = UNSET,

) -> HTTPValidationError | PageApiKeyRead | None:
    """ List API keys

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        enabled (bool | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageApiKeyRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
enabled=enabled,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    enabled: bool | None | Unset = UNSET,

) -> Response[HTTPValidationError | PageApiKeyRead]:
    """ List API keys

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        enabled (bool | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageApiKeyRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
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
    enabled: bool | None | Unset = UNSET,

) -> HTTPValidationError | PageApiKeyRead | None:
    """ List API keys

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        enabled (bool | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageApiKeyRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
enabled=enabled,

    )).parsed
