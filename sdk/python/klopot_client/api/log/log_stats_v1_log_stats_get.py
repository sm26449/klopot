from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.log_stats_v1_log_stats_get_response_log_stats_v1_log_stats_get import LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    window: str | Unset = '24h',

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["window"] = window


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/log/stats",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet | None:
    if response.status_code == 200:
        response_200 = LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    window: str | Unset = '24h',

) -> Response[HTTPValidationError | LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet]:
    """ Aggregate counters over a recent window (dashboard)

     Grouped counts over the last ``window`` (e.g. 24h): dispatched vs suppressed-by-reason, by-severity,
    the busiest types, and the count of still-unacknowledged criticals. Indexed on fired_at.

    Args:
        window (str | Unset): e.g. 30m, 24h, 7d. Default: '24h'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet]
     """


    kwargs = _get_kwargs(
        window=window,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    window: str | Unset = '24h',

) -> HTTPValidationError | LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet | None:
    """ Aggregate counters over a recent window (dashboard)

     Grouped counts over the last ``window`` (e.g. 24h): dispatched vs suppressed-by-reason, by-severity,
    the busiest types, and the count of still-unacknowledged criticals. Indexed on fired_at.

    Args:
        window (str | Unset): e.g. 30m, 24h, 7d. Default: '24h'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet
     """


    return sync_detailed(
        client=client,
window=window,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    window: str | Unset = '24h',

) -> Response[HTTPValidationError | LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet]:
    """ Aggregate counters over a recent window (dashboard)

     Grouped counts over the last ``window`` (e.g. 24h): dispatched vs suppressed-by-reason, by-severity,
    the busiest types, and the count of still-unacknowledged criticals. Indexed on fired_at.

    Args:
        window (str | Unset): e.g. 30m, 24h, 7d. Default: '24h'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet]
     """


    kwargs = _get_kwargs(
        window=window,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    window: str | Unset = '24h',

) -> HTTPValidationError | LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet | None:
    """ Aggregate counters over a recent window (dashboard)

     Grouped counts over the last ``window`` (e.g. 24h): dispatched vs suppressed-by-reason, by-severity,
    the busiest types, and the count of still-unacknowledged criticals. Indexed on fired_at.

    Args:
        window (str | Unset): e.g. 30m, 24h, 7d. Default: '24h'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | LogStatsV1LogStatsGetResponseLogStatsV1LogStatsGet
     """


    return (await asyncio_detailed(
        client=client,
window=window,

    )).parsed
