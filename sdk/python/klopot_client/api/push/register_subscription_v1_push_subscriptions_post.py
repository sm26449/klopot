from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.push_subscription_create import PushSubscriptionCreate
from ...models.push_subscription_read import PushSubscriptionRead
from typing import cast



def _get_kwargs(
    *,
    body: PushSubscriptionCreate,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/push/subscriptions",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | HTTPValidationError | PushSubscriptionRead | None:
    if response.status_code == 200:
        response_200 = PushSubscriptionRead.from_dict(response.json())



        return response_200

    if response.status_code == 201:
        response_201 = cast(Any, None)
        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | HTTPValidationError | PushSubscriptionRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: PushSubscriptionCreate,

) -> Response[Any | HTTPValidationError | PushSubscriptionRead]:
    """ Register this browser / app

    Args:
        body (PushSubscriptionCreate): The browser's ``PushSubscription.toJSON()`` plus an
            optional label.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | PushSubscriptionRead]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    body: PushSubscriptionCreate,

) -> Any | HTTPValidationError | PushSubscriptionRead | None:
    """ Register this browser / app

    Args:
        body (PushSubscriptionCreate): The browser's ``PushSubscription.toJSON()`` plus an
            optional label.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | PushSubscriptionRead
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: PushSubscriptionCreate,

) -> Response[Any | HTTPValidationError | PushSubscriptionRead]:
    """ Register this browser / app

    Args:
        body (PushSubscriptionCreate): The browser's ``PushSubscription.toJSON()`` plus an
            optional label.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | PushSubscriptionRead]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    body: PushSubscriptionCreate,

) -> Any | HTTPValidationError | PushSubscriptionRead | None:
    """ Register this browser / app

    Args:
        body (PushSubscriptionCreate): The browser's ``PushSubscription.toJSON()`` plus an
            optional label.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | PushSubscriptionRead
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
