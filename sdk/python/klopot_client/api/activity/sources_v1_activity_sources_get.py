from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.sources_response import SourcesResponse
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    hours: int | Unset = 24,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["hours"] = hours


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/activity/sources",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | SourcesResponse | None:
    if response.status_code == 200:
        response_200 = SourcesResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | SourcesResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    hours: int | Unset = 24,

) -> Response[HTTPValidationError | SourcesResponse]:
    """ Who sent what, grouped

    Args:
        hours (int | Unset):  Default: 24.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SourcesResponse]
     """


    kwargs = _get_kwargs(
        hours=hours,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    hours: int | Unset = 24,

) -> HTTPValidationError | SourcesResponse | None:
    """ Who sent what, grouped

    Args:
        hours (int | Unset):  Default: 24.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SourcesResponse
     """


    return sync_detailed(
        client=client,
hours=hours,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    hours: int | Unset = 24,

) -> Response[HTTPValidationError | SourcesResponse]:
    """ Who sent what, grouped

    Args:
        hours (int | Unset):  Default: 24.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SourcesResponse]
     """


    kwargs = _get_kwargs(
        hours=hours,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    hours: int | Unset = 24,

) -> HTTPValidationError | SourcesResponse | None:
    """ Who sent what, grouped

    Args:
        hours (int | Unset):  Default: 24.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SourcesResponse
     """


    return (await asyncio_detailed(
        client=client,
hours=hours,

    )).parsed
