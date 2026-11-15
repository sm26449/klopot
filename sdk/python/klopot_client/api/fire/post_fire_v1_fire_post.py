from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.fire_request import FireRequest
from ...models.fire_response import FireResponse
from ...models.http_validation_error import HTTPValidationError
from typing import cast



def _get_kwargs(
    *,
    body: FireRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/fire",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> FireResponse | HTTPValidationError | None:
    if response.status_code == 202:
        response_202 = FireResponse.from_dict(response.json())



        return response_202

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
    *,
    client: AuthenticatedClient,
    body: FireRequest,

) -> Response[FireResponse | HTTPValidationError]:
    """ Fire a notification by type

     External callers (Node-RED, scripts, third-party apps) post here with `type` and `context` (vars
    used by the template). The service handles routing, throttling, and channel dispatch. Caller does
    NOT need to know channels, credentials, or templates.

    With `idempotency_key` the fire belongs to an **episode**: the first `status: firing` opens it (an
    incident) and notifies, repeats while it is open notify nothing, `status: resolved` closes it and
    sends `resolved_type` if one was given. `episode` in the response says what happened. `test: true`
    ignores the key.

    Args:
        body (FireRequest): Body for ``POST /v1/fire``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FireResponse | HTTPValidationError]
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
    body: FireRequest,

) -> FireResponse | HTTPValidationError | None:
    """ Fire a notification by type

     External callers (Node-RED, scripts, third-party apps) post here with `type` and `context` (vars
    used by the template). The service handles routing, throttling, and channel dispatch. Caller does
    NOT need to know channels, credentials, or templates.

    With `idempotency_key` the fire belongs to an **episode**: the first `status: firing` opens it (an
    incident) and notifies, repeats while it is open notify nothing, `status: resolved` closes it and
    sends `resolved_type` if one was given. `episode` in the response says what happened. `test: true`
    ignores the key.

    Args:
        body (FireRequest): Body for ``POST /v1/fire``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FireResponse | HTTPValidationError
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: FireRequest,

) -> Response[FireResponse | HTTPValidationError]:
    """ Fire a notification by type

     External callers (Node-RED, scripts, third-party apps) post here with `type` and `context` (vars
    used by the template). The service handles routing, throttling, and channel dispatch. Caller does
    NOT need to know channels, credentials, or templates.

    With `idempotency_key` the fire belongs to an **episode**: the first `status: firing` opens it (an
    incident) and notifies, repeats while it is open notify nothing, `status: resolved` closes it and
    sends `resolved_type` if one was given. `episode` in the response says what happened. `test: true`
    ignores the key.

    Args:
        body (FireRequest): Body for ``POST /v1/fire``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FireResponse | HTTPValidationError]
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
    body: FireRequest,

) -> FireResponse | HTTPValidationError | None:
    """ Fire a notification by type

     External callers (Node-RED, scripts, third-party apps) post here with `type` and `context` (vars
    used by the template). The service handles routing, throttling, and channel dispatch. Caller does
    NOT need to know channels, credentials, or templates.

    With `idempotency_key` the fire belongs to an **episode**: the first `status: firing` opens it (an
    incident) and notifies, repeats while it is open notify nothing, `status: resolved` closes it and
    sends `resolved_type` if one was given. `episode` in the response says what happened. `test: true`
    ignores the key.

    Args:
        body (FireRequest): Body for ``POST /v1/fire``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FireResponse | HTTPValidationError
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
