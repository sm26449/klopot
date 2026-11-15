from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.input_health import InputHealth
from typing import cast



def _get_kwargs(
    input_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/inputs/{input_id}/health".format(input_id=quote(str(input_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | InputHealth | None:
    if response.status_code == 200:
        response_200 = InputHealth.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | InputHealth]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    input_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | InputHealth]:
    """ Adapter health probe

    Args:
        input_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | InputHealth]
     """


    kwargs = _get_kwargs(
        input_id=input_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    input_id: int,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | InputHealth | None:
    """ Adapter health probe

    Args:
        input_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | InputHealth
     """


    return sync_detailed(
        input_id=input_id,
client=client,

    ).parsed

async def asyncio_detailed(
    input_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | InputHealth]:
    """ Adapter health probe

    Args:
        input_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | InputHealth]
     """


    kwargs = _get_kwargs(
        input_id=input_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    input_id: int,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | InputHealth | None:
    """ Adapter health probe

    Args:
        input_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | InputHealth
     """


    return (await asyncio_detailed(
        input_id=input_id,
client=client,

    )).parsed
