from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.page_attempt_read import PageAttemptRead
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    channel: None | str | Unset = UNSET,
    notification_id: None | str | Unset = UNSET,
    kind: None | str | Unset = UNSET,
    outcome: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_channel: None | str | Unset
    if isinstance(channel, Unset):
        json_channel = UNSET
    else:
        json_channel = channel
    params["channel"] = json_channel

    json_notification_id: None | str | Unset
    if isinstance(notification_id, Unset):
        json_notification_id = UNSET
    else:
        json_notification_id = notification_id
    params["notification_id"] = json_notification_id

    json_kind: None | str | Unset
    if isinstance(kind, Unset):
        json_kind = UNSET
    else:
        json_kind = kind
    params["kind"] = json_kind

    json_outcome: None | str | Unset
    if isinstance(outcome, Unset):
        json_outcome = UNSET
    else:
        json_outcome = outcome
    params["outcome"] = json_outcome


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/activity/attempts",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageAttemptRead | None:
    if response.status_code == 200:
        response_200 = PageAttemptRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageAttemptRead]:
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
    channel: None | str | Unset = UNSET,
    notification_id: None | str | Unset = UNSET,
    kind: None | str | Unset = UNSET,
    outcome: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageAttemptRead]:
    """ Attempts to hand messages to providers

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        channel (None | str | Unset):
        notification_id (None | str | Unset):
        kind (None | str | Unset): alert, escalation or test
        outcome (None | str | Unset): sent, failed, deferred, permanent or timeout

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageAttemptRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
channel=channel,
notification_id=notification_id,
kind=kind,
outcome=outcome,

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
    channel: None | str | Unset = UNSET,
    notification_id: None | str | Unset = UNSET,
    kind: None | str | Unset = UNSET,
    outcome: None | str | Unset = UNSET,

) -> HTTPValidationError | PageAttemptRead | None:
    """ Attempts to hand messages to providers

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        channel (None | str | Unset):
        notification_id (None | str | Unset):
        kind (None | str | Unset): alert, escalation or test
        outcome (None | str | Unset): sent, failed, deferred, permanent or timeout

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageAttemptRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
channel=channel,
notification_id=notification_id,
kind=kind,
outcome=outcome,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    channel: None | str | Unset = UNSET,
    notification_id: None | str | Unset = UNSET,
    kind: None | str | Unset = UNSET,
    outcome: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageAttemptRead]:
    """ Attempts to hand messages to providers

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        channel (None | str | Unset):
        notification_id (None | str | Unset):
        kind (None | str | Unset): alert, escalation or test
        outcome (None | str | Unset): sent, failed, deferred, permanent or timeout

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageAttemptRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
channel=channel,
notification_id=notification_id,
kind=kind,
outcome=outcome,

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
    channel: None | str | Unset = UNSET,
    notification_id: None | str | Unset = UNSET,
    kind: None | str | Unset = UNSET,
    outcome: None | str | Unset = UNSET,

) -> HTTPValidationError | PageAttemptRead | None:
    """ Attempts to hand messages to providers

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        channel (None | str | Unset):
        notification_id (None | str | Unset):
        kind (None | str | Unset): alert, escalation or test
        outcome (None | str | Unset): sent, failed, deferred, permanent or timeout

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageAttemptRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
channel=channel,
notification_id=notification_id,
kind=kind,
outcome=outcome,

    )).parsed
