from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.rule_read import RuleRead
from typing import cast



def _get_kwargs(
    name: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/rules/by-name/{name}".format(name=quote(str(name), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | RuleRead | None:
    if response.status_code == 200:
        response_200 = RuleRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | RuleRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    name: str,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | RuleRead]:
    """ Get rule by name

     Companion to ``GET /v1/rules/{rule_id}`` for callers that hold the rule name (config files, log
    analysis, UI URL routing) but not the auto-increment id. Mounted under ``/by-name/`` so it never
    collides with the integer-id route.

    Args:
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RuleRead]
     """


    kwargs = _get_kwargs(
        name=name,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    name: str,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | RuleRead | None:
    """ Get rule by name

     Companion to ``GET /v1/rules/{rule_id}`` for callers that hold the rule name (config files, log
    analysis, UI URL routing) but not the auto-increment id. Mounted under ``/by-name/`` so it never
    collides with the integer-id route.

    Args:
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RuleRead
     """


    return sync_detailed(
        name=name,
client=client,

    ).parsed

async def asyncio_detailed(
    name: str,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | RuleRead]:
    """ Get rule by name

     Companion to ``GET /v1/rules/{rule_id}`` for callers that hold the rule name (config files, log
    analysis, UI URL routing) but not the auto-increment id. Mounted under ``/by-name/`` so it never
    collides with the integer-id route.

    Args:
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RuleRead]
     """


    kwargs = _get_kwargs(
        name=name,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    name: str,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | RuleRead | None:
    """ Get rule by name

     Companion to ``GET /v1/rules/{rule_id}`` for callers that hold the rule name (config files, log
    analysis, UI URL routing) but not the auto-increment id. Mounted under ``/by-name/`` so it never
    collides with the integer-id route.

    Args:
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RuleRead
     """


    return (await asyncio_detailed(
        name=name,
client=client,

    )).parsed
