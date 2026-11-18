from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.error_detail import ErrorDetail
from ...models.error_envelope import ErrorEnvelope
from ...models.fire_request import FireRequest
from ...models.fire_response import FireResponse
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



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ErrorDetail | ErrorEnvelope | FireResponse | None:
    if response.status_code == 202:
        response_202 = FireResponse.from_dict(response.json())



        return response_202

    if response.status_code == 401:
        response_401 = ErrorDetail.from_dict(response.json())



        return response_401

    if response.status_code == 403:
        response_403 = ErrorDetail.from_dict(response.json())



        return response_403

    if response.status_code == 413:
        response_413 = ErrorEnvelope.from_dict(response.json())



        return response_413

    if response.status_code == 422:
        response_422 = ErrorDetail.from_dict(response.json())



        return response_422

    if response.status_code == 429:
        response_429 = ErrorDetail.from_dict(response.json())



        return response_429

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ErrorDetail | ErrorEnvelope | FireResponse]:
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

) -> Response[ErrorDetail | ErrorEnvelope | FireResponse]:
    """ Fire a notification by type

     External callers (Node-RED, scripts, third-party apps) post here with `type` and `context` (vars
    used by the template). The service handles routing, throttling, and channel dispatch. Caller does
    NOT need to know channels, credentials, or templates.

    With `idempotency_key` the fire belongs to an **episode**: the first `status: firing` opens it (an
    incident) and notifies, repeats while it is open notify nothing, `status: resolved` closes it and
    sends `resolved_type` if one was given. `episode` in the response says what happened. `test: true`
    ignores the key.

    `test: true` marks the notification as a test. Only an `admin` caller's test also skips throttle,
    quiet hours and de-duplication; a `fire` key's test is gated like any other fire —
    `suppressed_reason` says why one was held.

    Args:
        body (FireRequest): Body for ``POST /v1/fire``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorDetail | ErrorEnvelope | FireResponse]
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

) -> ErrorDetail | ErrorEnvelope | FireResponse | None:
    """ Fire a notification by type

     External callers (Node-RED, scripts, third-party apps) post here with `type` and `context` (vars
    used by the template). The service handles routing, throttling, and channel dispatch. Caller does
    NOT need to know channels, credentials, or templates.

    With `idempotency_key` the fire belongs to an **episode**: the first `status: firing` opens it (an
    incident) and notifies, repeats while it is open notify nothing, `status: resolved` closes it and
    sends `resolved_type` if one was given. `episode` in the response says what happened. `test: true`
    ignores the key.

    `test: true` marks the notification as a test. Only an `admin` caller's test also skips throttle,
    quiet hours and de-duplication; a `fire` key's test is gated like any other fire —
    `suppressed_reason` says why one was held.

    Args:
        body (FireRequest): Body for ``POST /v1/fire``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorDetail | ErrorEnvelope | FireResponse
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: FireRequest,

) -> Response[ErrorDetail | ErrorEnvelope | FireResponse]:
    """ Fire a notification by type

     External callers (Node-RED, scripts, third-party apps) post here with `type` and `context` (vars
    used by the template). The service handles routing, throttling, and channel dispatch. Caller does
    NOT need to know channels, credentials, or templates.

    With `idempotency_key` the fire belongs to an **episode**: the first `status: firing` opens it (an
    incident) and notifies, repeats while it is open notify nothing, `status: resolved` closes it and
    sends `resolved_type` if one was given. `episode` in the response says what happened. `test: true`
    ignores the key.

    `test: true` marks the notification as a test. Only an `admin` caller's test also skips throttle,
    quiet hours and de-duplication; a `fire` key's test is gated like any other fire —
    `suppressed_reason` says why one was held.

    Args:
        body (FireRequest): Body for ``POST /v1/fire``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorDetail | ErrorEnvelope | FireResponse]
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

) -> ErrorDetail | ErrorEnvelope | FireResponse | None:
    """ Fire a notification by type

     External callers (Node-RED, scripts, third-party apps) post here with `type` and `context` (vars
    used by the template). The service handles routing, throttling, and channel dispatch. Caller does
    NOT need to know channels, credentials, or templates.

    With `idempotency_key` the fire belongs to an **episode**: the first `status: firing` opens it (an
    incident) and notifies, repeats while it is open notify nothing, `status: resolved` closes it and
    sends `resolved_type` if one was given. `episode` in the response says what happened. `test: true`
    ignores the key.

    `test: true` marks the notification as a test. Only an `admin` caller's test also skips throttle,
    quiet hours and de-duplication; a `fire` key's test is gated like any other fire —
    `suppressed_reason` says why one was held.

    Args:
        body (FireRequest): Body for ``POST /v1/fire``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorDetail | ErrorEnvelope | FireResponse
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
