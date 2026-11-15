from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.page_template_read import PageTemplateRead
from ...models.severity import Severity
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    severity: None | Severity | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    category: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_severity: None | str | Unset
    if isinstance(severity, Unset):
        json_severity = UNSET
    elif isinstance(severity, Severity):
        json_severity = severity.value
    else:
        json_severity = severity
    params["severity"] = json_severity

    json_enabled: bool | None | Unset
    if isinstance(enabled, Unset):
        json_enabled = UNSET
    else:
        json_enabled = enabled
    params["enabled"] = json_enabled

    json_category: None | str | Unset
    if isinstance(category, Unset):
        json_category = UNSET
    else:
        json_category = category
    params["category"] = json_category

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/templates",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageTemplateRead | None:
    if response.status_code == 200:
        response_200 = PageTemplateRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageTemplateRead]:
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
    severity: None | Severity | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    category: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageTemplateRead]:
    """ List templates

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        severity (None | Severity | Unset):
        enabled (bool | None | Unset):
        category (None | str | Unset): Filter by category (e.g. 'Storage'). Pass '__none__' to
            select uncategorized templates.
        search (None | str | Unset): Free-text match on type / title / category.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageTemplateRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
severity=severity,
enabled=enabled,
category=category,
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
    limit: int | Unset = 50,
    severity: None | Severity | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    category: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> HTTPValidationError | PageTemplateRead | None:
    """ List templates

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        severity (None | Severity | Unset):
        enabled (bool | None | Unset):
        category (None | str | Unset): Filter by category (e.g. 'Storage'). Pass '__none__' to
            select uncategorized templates.
        search (None | str | Unset): Free-text match on type / title / category.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageTemplateRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
severity=severity,
enabled=enabled,
category=category,
search=search,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    severity: None | Severity | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    category: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageTemplateRead]:
    """ List templates

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        severity (None | Severity | Unset):
        enabled (bool | None | Unset):
        category (None | str | Unset): Filter by category (e.g. 'Storage'). Pass '__none__' to
            select uncategorized templates.
        search (None | str | Unset): Free-text match on type / title / category.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageTemplateRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
severity=severity,
enabled=enabled,
category=category,
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
    limit: int | Unset = 50,
    severity: None | Severity | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    category: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> HTTPValidationError | PageTemplateRead | None:
    """ List templates

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        severity (None | Severity | Unset):
        enabled (bool | None | Unset):
        category (None | str | Unset): Filter by category (e.g. 'Storage'). Pass '__none__' to
            select uncategorized templates.
        search (None | str | Unset): Free-text match on type / title / category.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageTemplateRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
severity=severity,
enabled=enabled,
category=category,
search=search,

    )).parsed
