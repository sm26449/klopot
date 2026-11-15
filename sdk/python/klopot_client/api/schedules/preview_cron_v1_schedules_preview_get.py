from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.preview_cron_v1_schedules_preview_get_response_preview_cron_v1_schedules_preview_get import PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    cron: str,
    n: int | Unset = 5,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["cron"] = cron

    params["n"] = n


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/schedules/preview",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet | None:
    if response.status_code == 200:
        response_200 = PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    cron: str,
    n: int | Unset = 5,

) -> Response[HTTPValidationError | PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet]:
    """ Preview the next N firings of a cron expression

     Validates a cron expression and returns its next ``n`` firing times in the service timezone — used
    by the schedule editor before saving. Pure: touches no schedule row.

    Args:
        cron (str): 5-field cron expression.
        n (int | Unset):  Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet]
     """


    kwargs = _get_kwargs(
        cron=cron,
n=n,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    cron: str,
    n: int | Unset = 5,

) -> HTTPValidationError | PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet | None:
    """ Preview the next N firings of a cron expression

     Validates a cron expression and returns its next ``n`` firing times in the service timezone — used
    by the schedule editor before saving. Pure: touches no schedule row.

    Args:
        cron (str): 5-field cron expression.
        n (int | Unset):  Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet
     """


    return sync_detailed(
        client=client,
cron=cron,
n=n,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    cron: str,
    n: int | Unset = 5,

) -> Response[HTTPValidationError | PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet]:
    """ Preview the next N firings of a cron expression

     Validates a cron expression and returns its next ``n`` firing times in the service timezone — used
    by the schedule editor before saving. Pure: touches no schedule row.

    Args:
        cron (str): 5-field cron expression.
        n (int | Unset):  Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet]
     """


    kwargs = _get_kwargs(
        cron=cron,
n=n,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    cron: str,
    n: int | Unset = 5,

) -> HTTPValidationError | PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet | None:
    """ Preview the next N firings of a cron expression

     Validates a cron expression and returns its next ``n`` firing times in the service timezone — used
    by the schedule editor before saving. Pure: touches no schedule row.

    Args:
        cron (str): 5-field cron expression.
        n (int | Unset):  Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PreviewCronV1SchedulesPreviewGetResponsePreviewCronV1SchedulesPreviewGet
     """


    return (await asyncio_detailed(
        client=client,
cron=cron,
n=n,

    )).parsed
