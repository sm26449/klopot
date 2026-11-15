from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.fire_response import FireResponse
from ...models.http_validation_error import HTTPValidationError
from typing import cast



def _get_kwargs(
    schedule_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/schedules/{schedule_id}/test".format(schedule_id=quote(str(schedule_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> FireResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FireResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[FireResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    schedule_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[FireResponse | HTTPValidationError]:
    """ Fire the schedule's template once now (test=True, bypass throttle)

    Args:
        schedule_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FireResponse | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        schedule_id=schedule_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    schedule_id: int,
    *,
    client: AuthenticatedClient,

) -> FireResponse | HTTPValidationError | None:
    """ Fire the schedule's template once now (test=True, bypass throttle)

    Args:
        schedule_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FireResponse | HTTPValidationError
     """


    return sync_detailed(
        schedule_id=schedule_id,
client=client,

    ).parsed

async def asyncio_detailed(
    schedule_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[FireResponse | HTTPValidationError]:
    """ Fire the schedule's template once now (test=True, bypass throttle)

    Args:
        schedule_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FireResponse | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        schedule_id=schedule_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    schedule_id: int,
    *,
    client: AuthenticatedClient,

) -> FireResponse | HTTPValidationError | None:
    """ Fire the schedule's template once now (test=True, bypass throttle)

    Args:
        schedule_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FireResponse | HTTPValidationError
     """


    return (await asyncio_detailed(
        schedule_id=schedule_id,
client=client,

    )).parsed
