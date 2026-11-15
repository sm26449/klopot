from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.test_channel_v1_channels_channel_id_test_post_response_test_channel_v1_channels_channel_id_test_post import TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost
from typing import cast



def _get_kwargs(
    channel_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/channels/{channel_id}/test".format(channel_id=quote(str(channel_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost | None:
    if response.status_code == 200:
        response_200 = TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost]:
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

) -> Response[HTTPValidationError | TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost]:
    """ Send a test notification through this channel

     Bypasses templates / rules / gating — directly invokes the channel adapter with a synthetic
    Notification. Useful to verify credentials and reachability.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost]
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

) -> HTTPValidationError | TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost | None:
    """ Send a test notification through this channel

     Bypasses templates / rules / gating — directly invokes the channel adapter with a synthetic
    Notification. Useful to verify credentials and reachability.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost
     """


    return sync_detailed(
        channel_id=channel_id,
client=client,

    ).parsed

async def asyncio_detailed(
    channel_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost]:
    """ Send a test notification through this channel

     Bypasses templates / rules / gating — directly invokes the channel adapter with a synthetic
    Notification. Useful to verify credentials and reachability.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost]
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

) -> HTTPValidationError | TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost | None:
    """ Send a test notification through this channel

     Bypasses templates / rules / gating — directly invokes the channel adapter with a synthetic
    Notification. Useful to verify credentials and reachability.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TestChannelV1ChannelsChannelIdTestPostResponseTestChannelV1ChannelsChannelIdTestPost
     """


    return (await asyncio_detailed(
        channel_id=channel_id,
client=client,

    )).parsed
