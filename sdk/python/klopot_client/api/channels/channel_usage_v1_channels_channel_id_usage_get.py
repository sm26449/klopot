from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.channel_usage import ChannelUsage
from ...models.http_validation_error import HTTPValidationError
from typing import cast



def _get_kwargs(
    channel_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/channels/{channel_id}/usage".format(channel_id=quote(str(channel_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ChannelUsage | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ChannelUsage.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ChannelUsage | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    channel_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[ChannelUsage | HTTPValidationError]:
    """ Templates that route to this channel

     Lists the templates whose routing includes this channel. A non-empty list blocks ``DELETE`` (409
    CHANNEL_IN_USE) — the UI shows these so the operator unlinks them first.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChannelUsage | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        channel_id=channel_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    channel_id: int,
    *,
    client: AuthenticatedClient,

) -> ChannelUsage | HTTPValidationError | None:
    """ Templates that route to this channel

     Lists the templates whose routing includes this channel. A non-empty list blocks ``DELETE`` (409
    CHANNEL_IN_USE) — the UI shows these so the operator unlinks them first.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChannelUsage | HTTPValidationError
     """


    return sync_detailed(
        channel_id=channel_id,
client=client,

    ).parsed

async def asyncio_detailed(
    channel_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[ChannelUsage | HTTPValidationError]:
    """ Templates that route to this channel

     Lists the templates whose routing includes this channel. A non-empty list blocks ``DELETE`` (409
    CHANNEL_IN_USE) — the UI shows these so the operator unlinks them first.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChannelUsage | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        channel_id=channel_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    channel_id: int,
    *,
    client: AuthenticatedClient,

) -> ChannelUsage | HTTPValidationError | None:
    """ Templates that route to this channel

     Lists the templates whose routing includes this channel. A non-empty list blocks ``DELETE`` (409
    CHANNEL_IN_USE) — the UI shows these so the operator unlinks them first.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChannelUsage | HTTPValidationError
     """


    return (await asyncio_detailed(
        channel_id=channel_id,
client=client,

    )).parsed
