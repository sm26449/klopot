from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.pack_detail import PackDetail
from typing import cast



def _get_kwargs(
    pack_id: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/packs/{pack_id}".format(pack_id=quote(str(pack_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PackDetail | None:
    if response.status_code == 200:
        response_200 = PackDetail.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PackDetail]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    pack_id: str,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | PackDetail]:
    """ Get a built-in pack (summary + YAML)

    Args:
        pack_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PackDetail]
     """


    kwargs = _get_kwargs(
        pack_id=pack_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    pack_id: str,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | PackDetail | None:
    """ Get a built-in pack (summary + YAML)

    Args:
        pack_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PackDetail
     """


    return sync_detailed(
        pack_id=pack_id,
client=client,

    ).parsed

async def asyncio_detailed(
    pack_id: str,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | PackDetail]:
    """ Get a built-in pack (summary + YAML)

    Args:
        pack_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PackDetail]
     """


    kwargs = _get_kwargs(
        pack_id=pack_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    pack_id: str,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | PackDetail | None:
    """ Get a built-in pack (summary + YAML)

    Args:
        pack_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PackDetail
     """


    return (await asyncio_detailed(
        pack_id=pack_id,
client=client,

    )).parsed
