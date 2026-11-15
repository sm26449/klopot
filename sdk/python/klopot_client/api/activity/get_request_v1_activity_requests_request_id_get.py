from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_request_detail import ApiRequestDetail
from ...models.http_validation_error import HTTPValidationError
from typing import cast



def _get_kwargs(
    request_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/activity/requests/{request_id}".format(request_id=quote(str(request_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiRequestDetail | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ApiRequestDetail.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiRequestDetail | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    request_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[ApiRequestDetail | HTTPValidationError]:
    """ One request, with its bodies

    Args:
        request_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiRequestDetail | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        request_id=request_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    request_id: int,
    *,
    client: AuthenticatedClient,

) -> ApiRequestDetail | HTTPValidationError | None:
    """ One request, with its bodies

    Args:
        request_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiRequestDetail | HTTPValidationError
     """


    return sync_detailed(
        request_id=request_id,
client=client,

    ).parsed

async def asyncio_detailed(
    request_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[ApiRequestDetail | HTTPValidationError]:
    """ One request, with its bodies

    Args:
        request_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiRequestDetail | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        request_id=request_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    request_id: int,
    *,
    client: AuthenticatedClient,

) -> ApiRequestDetail | HTTPValidationError | None:
    """ One request, with its bodies

    Args:
        request_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiRequestDetail | HTTPValidationError
     """


    return (await asyncio_detailed(
        request_id=request_id,
client=client,

    )).parsed
