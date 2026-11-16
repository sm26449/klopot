from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.health_response import HealthResponse
from ...models.health_status import HealthStatus
from typing import cast



def _get_kwargs(
    
) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/health/ready",
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HealthResponse | HealthStatus | None:
    if response.status_code == 200:
        def _parse_response_200(data: object) -> HealthResponse | HealthStatus:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_200_type_0 = HealthResponse.from_dict(data)



                return response_200_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            response_200_type_1 = HealthStatus.from_dict(data)



            return response_200_type_1

        response_200 = _parse_response_200(response.json())

        return response_200

    if response.status_code == 503:
        def _parse_response_503(data: object) -> HealthResponse | HealthStatus:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_503_type_0 = HealthResponse.from_dict(data)



                return response_503_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            response_503_type_1 = HealthStatus.from_dict(data)



            return response_503_type_1

        response_503 = _parse_response_503(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HealthResponse | HealthStatus]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[HealthResponse | HealthStatus]:
    """ Readiness probe (fails on essential outages)

     Returns HTTP 200 when every essential component (database, rule engine, delivery worker) is up, and
    HTTP 503 when one is down — so an orchestrator or the container healthcheck acts on a dead engine or
    retry worker instead of a body that always says 200 (F32). The body is shaped like `/v1/health`'s
    for the same caller.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HealthResponse | HealthStatus]
     """


    kwargs = _get_kwargs(
        
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,

) -> HealthResponse | HealthStatus | None:
    """ Readiness probe (fails on essential outages)

     Returns HTTP 200 when every essential component (database, rule engine, delivery worker) is up, and
    HTTP 503 when one is down — so an orchestrator or the container healthcheck acts on a dead engine or
    retry worker instead of a body that always says 200 (F32). The body is shaped like `/v1/health`'s
    for the same caller.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HealthResponse | HealthStatus
     """


    return sync_detailed(
        client=client,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[HealthResponse | HealthStatus]:
    """ Readiness probe (fails on essential outages)

     Returns HTTP 200 when every essential component (database, rule engine, delivery worker) is up, and
    HTTP 503 when one is down — so an orchestrator or the container healthcheck acts on a dead engine or
    retry worker instead of a body that always says 200 (F32). The body is shaped like `/v1/health`'s
    for the same caller.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HealthResponse | HealthStatus]
     """


    kwargs = _get_kwargs(
        
    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,

) -> HealthResponse | HealthStatus | None:
    """ Readiness probe (fails on essential outages)

     Returns HTTP 200 when every essential component (database, rule engine, delivery worker) is up, and
    HTTP 503 when one is down — so an orchestrator or the container healthcheck acts on a dead engine or
    retry worker instead of a body that always says 200 (F32). The body is shaped like `/v1/health`'s
    for the same caller.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HealthResponse | HealthStatus
     """


    return (await asyncio_detailed(
        client=client,

    )).parsed
