from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.rule_bulk_enabled import RuleBulkEnabled
from ...models.rule_bulk_result import RuleBulkResult
from typing import cast



def _get_kwargs(
    *,
    body: RuleBulkEnabled,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/rules/bulk/enabled",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | RuleBulkResult | None:
    if response.status_code == 200:
        response_200 = RuleBulkResult.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | RuleBulkResult]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: RuleBulkEnabled,

) -> Response[HTTPValidationError | RuleBulkResult]:
    """ Enable or disable several rules

     One transaction, one audit entry per changed rule, one engine reload —
    instead of a PATCH (and a reload) per rule from the admin UI's bulk bar.

    Args:
        body (RuleBulkEnabled): Enable or disable several rules in one transaction (one engine
            reload).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RuleBulkResult]
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
    body: RuleBulkEnabled,

) -> HTTPValidationError | RuleBulkResult | None:
    """ Enable or disable several rules

     One transaction, one audit entry per changed rule, one engine reload —
    instead of a PATCH (and a reload) per rule from the admin UI's bulk bar.

    Args:
        body (RuleBulkEnabled): Enable or disable several rules in one transaction (one engine
            reload).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RuleBulkResult
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: RuleBulkEnabled,

) -> Response[HTTPValidationError | RuleBulkResult]:
    """ Enable or disable several rules

     One transaction, one audit entry per changed rule, one engine reload —
    instead of a PATCH (and a reload) per rule from the admin UI's bulk bar.

    Args:
        body (RuleBulkEnabled): Enable or disable several rules in one transaction (one engine
            reload).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RuleBulkResult]
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
    body: RuleBulkEnabled,

) -> HTTPValidationError | RuleBulkResult | None:
    """ Enable or disable several rules

     One transaction, one audit entry per changed rule, one engine reload —
    instead of a PATCH (and a reload) per rule from the admin UI's bulk bar.

    Args:
        body (RuleBulkEnabled): Enable or disable several rules in one transaction (one engine
            reload).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RuleBulkResult
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
