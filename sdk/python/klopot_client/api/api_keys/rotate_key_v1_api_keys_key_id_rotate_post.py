from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.api_key_created import ApiKeyCreated
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    key_id: int,
    *,
    grace_sec: int | Unset = 0,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["grace_sec"] = grace_sec


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/api_keys/{key_id}/rotate".format(key_id=quote(str(key_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApiKeyCreated | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ApiKeyCreated.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApiKeyCreated | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    key_id: int,
    *,
    client: AuthenticatedClient,
    grace_sec: int | Unset = 0,

) -> Response[ApiKeyCreated | HTTPValidationError]:
    """ Rotate (issue a new plaintext key, revoke the old)

    Args:
        key_id (int):
        grace_sec (int | Unset): Keep the old key valid for this many seconds (grace period)
            instead of revoking it immediately. Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiKeyCreated | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        key_id=key_id,
grace_sec=grace_sec,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    key_id: int,
    *,
    client: AuthenticatedClient,
    grace_sec: int | Unset = 0,

) -> ApiKeyCreated | HTTPValidationError | None:
    """ Rotate (issue a new plaintext key, revoke the old)

    Args:
        key_id (int):
        grace_sec (int | Unset): Keep the old key valid for this many seconds (grace period)
            instead of revoking it immediately. Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiKeyCreated | HTTPValidationError
     """


    return sync_detailed(
        key_id=key_id,
client=client,
grace_sec=grace_sec,

    ).parsed

async def asyncio_detailed(
    key_id: int,
    *,
    client: AuthenticatedClient,
    grace_sec: int | Unset = 0,

) -> Response[ApiKeyCreated | HTTPValidationError]:
    """ Rotate (issue a new plaintext key, revoke the old)

    Args:
        key_id (int):
        grace_sec (int | Unset): Keep the old key valid for this many seconds (grace period)
            instead of revoking it immediately. Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiKeyCreated | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        key_id=key_id,
grace_sec=grace_sec,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    key_id: int,
    *,
    client: AuthenticatedClient,
    grace_sec: int | Unset = 0,

) -> ApiKeyCreated | HTTPValidationError | None:
    """ Rotate (issue a new plaintext key, revoke the old)

    Args:
        key_id (int):
        grace_sec (int | Unset): Keep the old key valid for this many seconds (grace period)
            instead of revoking it immediately. Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiKeyCreated | HTTPValidationError
     """


    return (await asyncio_detailed(
        key_id=key_id,
client=client,
grace_sec=grace_sec,

    )).parsed
