from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.page_system_event_read import PageSystemEventRead
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    source_kind: None | str | Unset = UNSET,
    source_name: None | str | Unset = UNSET,
    event: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_source_kind: None | str | Unset
    if isinstance(source_kind, Unset):
        json_source_kind = UNSET
    else:
        json_source_kind = source_kind
    params["source_kind"] = json_source_kind

    json_source_name: None | str | Unset
    if isinstance(source_name, Unset):
        json_source_name = UNSET
    else:
        json_source_name = source_name
    params["source_name"] = json_source_name

    json_event: None | str | Unset
    if isinstance(event, Unset):
        json_event = UNSET
    else:
        json_event = event
    params["event"] = json_event


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/activity/events",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageSystemEventRead | None:
    if response.status_code == 200:
        response_200 = PageSystemEventRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageSystemEventRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    source_kind: None | str | Unset = UNSET,
    source_name: None | str | Unset = UNSET,
    event: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageSystemEventRead]:
    """ State changes of inputs, rules and channels

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        source_kind (None | str | Unset): input, rule or channel
        source_name (None | str | Unset):
        event (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageSystemEventRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
source_kind=source_kind,
source_name=source_name,
event=event,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    source_kind: None | str | Unset = UNSET,
    source_name: None | str | Unset = UNSET,
    event: None | str | Unset = UNSET,

) -> HTTPValidationError | PageSystemEventRead | None:
    """ State changes of inputs, rules and channels

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        source_kind (None | str | Unset): input, rule or channel
        source_name (None | str | Unset):
        event (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageSystemEventRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
source_kind=source_kind,
source_name=source_name,
event=event,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    source_kind: None | str | Unset = UNSET,
    source_name: None | str | Unset = UNSET,
    event: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageSystemEventRead]:
    """ State changes of inputs, rules and channels

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        source_kind (None | str | Unset): input, rule or channel
        source_name (None | str | Unset):
        event (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageSystemEventRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
source_kind=source_kind,
source_name=source_name,
event=event,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    source_kind: None | str | Unset = UNSET,
    source_name: None | str | Unset = UNSET,
    event: None | str | Unset = UNSET,

) -> HTTPValidationError | PageSystemEventRead | None:
    """ State changes of inputs, rules and channels

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        source_kind (None | str | Unset): input, rule or channel
        source_name (None | str | Unset):
        event (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageSystemEventRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
source_kind=source_kind,
source_name=source_name,
event=event,

    )).parsed
