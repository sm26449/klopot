from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.reset_breaker_v1_channels_channel_id_breaker_reset_post_response_reset_breaker_v1_channels_channel_id_breaker_reset_post import ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost
from typing import cast



def _get_kwargs(
    channel_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/channels/{channel_id}/breaker/reset".format(channel_id=quote(str(channel_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost | None:
    if response.status_code == 200:
        response_200 = ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost]:
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

) -> Response[HTTPValidationError | ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost]:
    """ Force this channel's circuit breaker closed

     Clears the open window and failure count so the next send is attempted immediately. Use after fixing
    the underlying cause (e.g. rotated a revoked token). Audited as channel.breaker_reset.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost]
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

) -> HTTPValidationError | ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost | None:
    """ Force this channel's circuit breaker closed

     Clears the open window and failure count so the next send is attempted immediately. Use after fixing
    the underlying cause (e.g. rotated a revoked token). Audited as channel.breaker_reset.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost
     """


    return sync_detailed(
        channel_id=channel_id,
client=client,

    ).parsed

async def asyncio_detailed(
    channel_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost]:
    """ Force this channel's circuit breaker closed

     Clears the open window and failure count so the next send is attempted immediately. Use after fixing
    the underlying cause (e.g. rotated a revoked token). Audited as channel.breaker_reset.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost]
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

) -> HTTPValidationError | ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost | None:
    """ Force this channel's circuit breaker closed

     Clears the open window and failure count so the next send is attempted immediately. Use after fixing
    the underlying cause (e.g. rotated a revoked token). Audited as channel.breaker_reset.

    Args:
        channel_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResetBreakerV1ChannelsChannelIdBreakerResetPostResponseResetBreakerV1ChannelsChannelIdBreakerResetPost
     """


    return (await asyncio_detailed(
        channel_id=channel_id,
client=client,

    )).parsed
