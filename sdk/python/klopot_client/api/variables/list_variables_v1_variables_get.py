from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.list_variables_v1_variables_get_state_type_0 import ListVariablesV1VariablesGetStateType0
from ...models.page_variable_read import PageVariableRead
from ...models.variable_source import VariableSource
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 100,
    source: None | Unset | VariableSource = UNSET,
    enabled: bool | None | Unset = UNSET,
    stale: bool | None | Unset = UNSET,
    state: ListVariablesV1VariablesGetStateType0 | None | Unset = UNSET,
    input_id: int | None | Unset = UNSET,
    used: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_source: None | str | Unset
    if isinstance(source, Unset):
        json_source = UNSET
    elif isinstance(source, VariableSource):
        json_source = source.value
    else:
        json_source = source
    params["source"] = json_source

    json_enabled: bool | None | Unset
    if isinstance(enabled, Unset):
        json_enabled = UNSET
    else:
        json_enabled = enabled
    params["enabled"] = json_enabled

    json_stale: bool | None | Unset
    if isinstance(stale, Unset):
        json_stale = UNSET
    else:
        json_stale = stale
    params["stale"] = json_stale

    json_state: None | str | Unset
    if isinstance(state, Unset):
        json_state = UNSET
    elif isinstance(state, ListVariablesV1VariablesGetStateType0):
        json_state = state.value
    else:
        json_state = state
    params["state"] = json_state

    json_input_id: int | None | Unset
    if isinstance(input_id, Unset):
        json_input_id = UNSET
    else:
        json_input_id = input_id
    params["input_id"] = json_input_id

    json_used: bool | None | Unset
    if isinstance(used, Unset):
        json_used = UNSET
    else:
        json_used = used
    params["used"] = json_used

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/variables",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageVariableRead | None:
    if response.status_code == 200:
        response_200 = PageVariableRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageVariableRead]:
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
    limit: int | Unset = 100,
    source: None | Unset | VariableSource = UNSET,
    enabled: bool | None | Unset = UNSET,
    stale: bool | None | Unset = UNSET,
    state: ListVariablesV1VariablesGetStateType0 | None | Unset = UNSET,
    input_id: int | None | Unset = UNSET,
    used: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageVariableRead]:
    """ List variables

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 100.
        source (None | Unset | VariableSource):
        enabled (bool | None | Unset):
        stale (bool | None | Unset): Filter on live staleness (runtime, not a DB column).
        state (ListVariablesV1VariablesGetStateType0 | None | Unset): Filter on value_state:
            fresh, stale, or missing (no value since start-up).
        input_id (int | None | Unset): Only variables fed by this input.
        used (bool | None | Unset): true → read by at least one rule or computed variable; false →
            unused.
        search (None | str | Unset): Free-text match on name / description.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageVariableRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
source=source,
enabled=enabled,
stale=stale,
state=state,
input_id=input_id,
used=used,
search=search,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 100,
    source: None | Unset | VariableSource = UNSET,
    enabled: bool | None | Unset = UNSET,
    stale: bool | None | Unset = UNSET,
    state: ListVariablesV1VariablesGetStateType0 | None | Unset = UNSET,
    input_id: int | None | Unset = UNSET,
    used: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> HTTPValidationError | PageVariableRead | None:
    """ List variables

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 100.
        source (None | Unset | VariableSource):
        enabled (bool | None | Unset):
        stale (bool | None | Unset): Filter on live staleness (runtime, not a DB column).
        state (ListVariablesV1VariablesGetStateType0 | None | Unset): Filter on value_state:
            fresh, stale, or missing (no value since start-up).
        input_id (int | None | Unset): Only variables fed by this input.
        used (bool | None | Unset): true → read by at least one rule or computed variable; false →
            unused.
        search (None | str | Unset): Free-text match on name / description.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageVariableRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
source=source,
enabled=enabled,
stale=stale,
state=state,
input_id=input_id,
used=used,
search=search,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 100,
    source: None | Unset | VariableSource = UNSET,
    enabled: bool | None | Unset = UNSET,
    stale: bool | None | Unset = UNSET,
    state: ListVariablesV1VariablesGetStateType0 | None | Unset = UNSET,
    input_id: int | None | Unset = UNSET,
    used: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageVariableRead]:
    """ List variables

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 100.
        source (None | Unset | VariableSource):
        enabled (bool | None | Unset):
        stale (bool | None | Unset): Filter on live staleness (runtime, not a DB column).
        state (ListVariablesV1VariablesGetStateType0 | None | Unset): Filter on value_state:
            fresh, stale, or missing (no value since start-up).
        input_id (int | None | Unset): Only variables fed by this input.
        used (bool | None | Unset): true → read by at least one rule or computed variable; false →
            unused.
        search (None | str | Unset): Free-text match on name / description.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageVariableRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
source=source,
enabled=enabled,
stale=stale,
state=state,
input_id=input_id,
used=used,
search=search,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 100,
    source: None | Unset | VariableSource = UNSET,
    enabled: bool | None | Unset = UNSET,
    stale: bool | None | Unset = UNSET,
    state: ListVariablesV1VariablesGetStateType0 | None | Unset = UNSET,
    input_id: int | None | Unset = UNSET,
    used: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> HTTPValidationError | PageVariableRead | None:
    """ List variables

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 100.
        source (None | Unset | VariableSource):
        enabled (bool | None | Unset):
        stale (bool | None | Unset): Filter on live staleness (runtime, not a DB column).
        state (ListVariablesV1VariablesGetStateType0 | None | Unset): Filter on value_state:
            fresh, stale, or missing (no value since start-up).
        input_id (int | None | Unset): Only variables fed by this input.
        used (bool | None | Unset): true → read by at least one rule or computed variable; false →
            unused.
        search (None | str | Unset): Free-text match on name / description.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageVariableRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
source=source,
enabled=enabled,
stale=stale,
state=state,
input_id=input_id,
used=used,
search=search,

    )).parsed
