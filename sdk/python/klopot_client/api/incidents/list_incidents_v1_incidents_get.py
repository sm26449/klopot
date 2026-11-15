from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.list_incidents_v1_incidents_get_state_type_0 import ListIncidentsV1IncidentsGetStateType0
from ...models.page_incident_read import PageIncidentRead
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    state: ListIncidentsV1IncidentsGetStateType0 | None | Unset = UNSET,
    acknowledged: bool | None | Unset = UNSET,
    rule_id: int | None | Unset = UNSET,
    search: None | str | Unset = UNSET,
    skip: int | Unset = 0,
    limit: int | Unset = 50,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_state: None | str | Unset
    if isinstance(state, Unset):
        json_state = UNSET
    elif isinstance(state, ListIncidentsV1IncidentsGetStateType0):
        json_state = state.value
    else:
        json_state = state
    params["state"] = json_state

    json_acknowledged: bool | None | Unset
    if isinstance(acknowledged, Unset):
        json_acknowledged = UNSET
    else:
        json_acknowledged = acknowledged
    params["acknowledged"] = json_acknowledged

    json_rule_id: int | None | Unset
    if isinstance(rule_id, Unset):
        json_rule_id = UNSET
    else:
        json_rule_id = rule_id
    params["rule_id"] = json_rule_id

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search

    params["skip"] = skip

    params["limit"] = limit


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/incidents",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageIncidentRead | None:
    if response.status_code == 200:
        response_200 = PageIncidentRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageIncidentRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    state: ListIncidentsV1IncidentsGetStateType0 | None | Unset = UNSET,
    acknowledged: bool | None | Unset = UNSET,
    rule_id: int | None | Unset = UNSET,
    search: None | str | Unset = UNSET,
    skip: int | Unset = 0,
    limit: int | Unset = 50,

) -> Response[HTTPValidationError | PageIncidentRead]:
    """ List Incidents

    Args:
        state (ListIncidentsV1IncidentsGetStateType0 | None | Unset):
        acknowledged (bool | None | Unset):
        rule_id (int | None | Unset):
        search (None | str | Unset):
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageIncidentRead]
     """


    kwargs = _get_kwargs(
        state=state,
acknowledged=acknowledged,
rule_id=rule_id,
search=search,
skip=skip,
limit=limit,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    state: ListIncidentsV1IncidentsGetStateType0 | None | Unset = UNSET,
    acknowledged: bool | None | Unset = UNSET,
    rule_id: int | None | Unset = UNSET,
    search: None | str | Unset = UNSET,
    skip: int | Unset = 0,
    limit: int | Unset = 50,

) -> HTTPValidationError | PageIncidentRead | None:
    """ List Incidents

    Args:
        state (ListIncidentsV1IncidentsGetStateType0 | None | Unset):
        acknowledged (bool | None | Unset):
        rule_id (int | None | Unset):
        search (None | str | Unset):
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageIncidentRead
     """


    return sync_detailed(
        client=client,
state=state,
acknowledged=acknowledged,
rule_id=rule_id,
search=search,
skip=skip,
limit=limit,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    state: ListIncidentsV1IncidentsGetStateType0 | None | Unset = UNSET,
    acknowledged: bool | None | Unset = UNSET,
    rule_id: int | None | Unset = UNSET,
    search: None | str | Unset = UNSET,
    skip: int | Unset = 0,
    limit: int | Unset = 50,

) -> Response[HTTPValidationError | PageIncidentRead]:
    """ List Incidents

    Args:
        state (ListIncidentsV1IncidentsGetStateType0 | None | Unset):
        acknowledged (bool | None | Unset):
        rule_id (int | None | Unset):
        search (None | str | Unset):
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageIncidentRead]
     """


    kwargs = _get_kwargs(
        state=state,
acknowledged=acknowledged,
rule_id=rule_id,
search=search,
skip=skip,
limit=limit,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    state: ListIncidentsV1IncidentsGetStateType0 | None | Unset = UNSET,
    acknowledged: bool | None | Unset = UNSET,
    rule_id: int | None | Unset = UNSET,
    search: None | str | Unset = UNSET,
    skip: int | Unset = 0,
    limit: int | Unset = 50,

) -> HTTPValidationError | PageIncidentRead | None:
    """ List Incidents

    Args:
        state (ListIncidentsV1IncidentsGetStateType0 | None | Unset):
        acknowledged (bool | None | Unset):
        rule_id (int | None | Unset):
        search (None | str | Unset):
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageIncidentRead
     """


    return (await asyncio_detailed(
        client=client,
state=state,
acknowledged=acknowledged,
rule_id=rule_id,
search=search,
skip=skip,
limit=limit,

    )).parsed
