from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.channel_read import ChannelRead
from ...models.channel_update import ChannelUpdate
from ...models.http_validation_error import HTTPValidationError
from typing import cast



def _get_kwargs(
    channel_id: int,
    *,
    body: ChannelUpdate,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/v1/channels/{channel_id}".format(channel_id=quote(str(channel_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ChannelRead | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ChannelRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ChannelRead | HTTPValidationError]:
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
    body: ChannelUpdate,

) -> Response[ChannelRead | HTTPValidationError]:
    """ Update channel

    Args:
        channel_id (int):
        body (ChannelUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChannelRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        channel_id=channel_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    channel_id: int,
    *,
    client: AuthenticatedClient,
    body: ChannelUpdate,

) -> ChannelRead | HTTPValidationError | None:
    """ Update channel

    Args:
        channel_id (int):
        body (ChannelUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChannelRead | HTTPValidationError
     """


    return sync_detailed(
        channel_id=channel_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    channel_id: int,
    *,
    client: AuthenticatedClient,
    body: ChannelUpdate,

) -> Response[ChannelRead | HTTPValidationError]:
    """ Update channel

    Args:
        channel_id (int):
        body (ChannelUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChannelRead | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        channel_id=channel_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    channel_id: int,
    *,
    client: AuthenticatedClient,
    body: ChannelUpdate,

) -> ChannelRead | HTTPValidationError | None:
    """ Update channel

    Args:
        channel_id (int):
        body (ChannelUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChannelRead | HTTPValidationError
     """


    return (await asyncio_detailed(
        channel_id=channel_id,
client=client,
body=body,

    )).parsed
