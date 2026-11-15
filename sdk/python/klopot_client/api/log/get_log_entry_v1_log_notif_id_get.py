from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.log_entry_detail import LogEntryDetail
from typing import cast



def _get_kwargs(
    notif_id: str,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/log/{notif_id}".format(notif_id=quote(str(notif_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | LogEntryDetail | None:
    if response.status_code == 200:
        response_200 = LogEntryDetail.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | LogEntryDetail]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    notif_id: str,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | LogEntryDetail]:
    """ Get a single notification log entry

     Used by "why did this fire" views to display the rule that fired, the rendered template, channel
    dispatch result, and the full ``vars_payload`` snapshot.

    Args:
        notif_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | LogEntryDetail]
     """


    kwargs = _get_kwargs(
        notif_id=notif_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    notif_id: str,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | LogEntryDetail | None:
    """ Get a single notification log entry

     Used by "why did this fire" views to display the rule that fired, the rendered template, channel
    dispatch result, and the full ``vars_payload`` snapshot.

    Args:
        notif_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | LogEntryDetail
     """


    return sync_detailed(
        notif_id=notif_id,
client=client,

    ).parsed

async def asyncio_detailed(
    notif_id: str,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | LogEntryDetail]:
    """ Get a single notification log entry

     Used by "why did this fire" views to display the rule that fired, the rendered template, channel
    dispatch result, and the full ``vars_payload`` snapshot.

    Args:
        notif_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | LogEntryDetail]
     """


    kwargs = _get_kwargs(
        notif_id=notif_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    notif_id: str,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | LogEntryDetail | None:
    """ Get a single notification log entry

     Used by "why did this fire" views to display the rule that fired, the rendered template, channel
    dispatch result, and the full ``vars_payload`` snapshot.

    Args:
        notif_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | LogEntryDetail
     """


    return (await asyncio_detailed(
        notif_id=notif_id,
client=client,

    )).parsed
