from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.push_test_result import PushTestResult
from typing import cast



def _get_kwargs(
    sub_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/push/subscriptions/{sub_id}/test".format(sub_id=quote(str(sub_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PushTestResult | None:
    if response.status_code == 200:
        response_200 = PushTestResult.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PushTestResult]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    sub_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | PushTestResult]:
    """ Send a test to one device

    Args:
        sub_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PushTestResult]
     """


    kwargs = _get_kwargs(
        sub_id=sub_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    sub_id: int,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | PushTestResult | None:
    """ Send a test to one device

    Args:
        sub_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PushTestResult
     """


    return sync_detailed(
        sub_id=sub_id,
client=client,

    ).parsed

async def asyncio_detailed(
    sub_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | PushTestResult]:
    """ Send a test to one device

    Args:
        sub_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PushTestResult]
     """


    kwargs = _get_kwargs(
        sub_id=sub_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    sub_id: int,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | PushTestResult | None:
    """ Send a test to one device

    Args:
        sub_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PushTestResult
     """


    return (await asyncio_detailed(
        sub_id=sub_id,
client=client,

    )).parsed
