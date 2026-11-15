from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.list_rules_v1_rules_get_eval_status_type_0 import ListRulesV1RulesGetEvalStatusType0
from ...models.page_rule_read import PageRuleRead
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    template_type: None | str | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    has_error: bool | None | Unset = UNSET,
    eval_status: ListRulesV1RulesGetEvalStatusType0 | None | Unset = UNSET,
    category: None | str | Unset = UNSET,
    never_fired: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_template_type: None | str | Unset
    if isinstance(template_type, Unset):
        json_template_type = UNSET
    else:
        json_template_type = template_type
    params["template_type"] = json_template_type

    json_enabled: bool | None | Unset
    if isinstance(enabled, Unset):
        json_enabled = UNSET
    else:
        json_enabled = enabled
    params["enabled"] = json_enabled

    json_has_error: bool | None | Unset
    if isinstance(has_error, Unset):
        json_has_error = UNSET
    else:
        json_has_error = has_error
    params["has_error"] = json_has_error

    json_eval_status: None | str | Unset
    if isinstance(eval_status, Unset):
        json_eval_status = UNSET
    elif isinstance(eval_status, ListRulesV1RulesGetEvalStatusType0):
        json_eval_status = eval_status.value
    else:
        json_eval_status = eval_status
    params["eval_status"] = json_eval_status

    json_category: None | str | Unset
    if isinstance(category, Unset):
        json_category = UNSET
    else:
        json_category = category
    params["category"] = json_category

    json_never_fired: bool | None | Unset
    if isinstance(never_fired, Unset):
        json_never_fired = UNSET
    else:
        json_never_fired = never_fired
    params["never_fired"] = json_never_fired

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/rules",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageRuleRead | None:
    if response.status_code == 200:
        response_200 = PageRuleRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageRuleRead]:
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
    template_type: None | str | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    has_error: bool | None | Unset = UNSET,
    eval_status: ListRulesV1RulesGetEvalStatusType0 | None | Unset = UNSET,
    category: None | str | Unset = UNSET,
    never_fired: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageRuleRead]:
    """ List rules

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        template_type (None | str | Unset):
        enabled (bool | None | Unset):
        has_error (bool | None | Unset): true → only rules whose expression fails
            (eval_status=error); false → the rest. A rule waiting for an input is eval_status=no_data.
        eval_status (ListRulesV1RulesGetEvalStatusType0 | None | Unset): ok | no_data (waiting for
            an input) | error (expression fails).
        category (None | str | Unset): Category of the rule's template (case-insensitive);
            '__none__' = uncategorized.
        never_fired (bool | None | Unset): true → rules that have never fired; false → rules that
            have.
        search (None | str | Unset): Free-text match on name / condition / summary.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageRuleRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
template_type=template_type,
enabled=enabled,
has_error=has_error,
eval_status=eval_status,
category=category,
never_fired=never_fired,
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
    template_type: None | str | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    has_error: bool | None | Unset = UNSET,
    eval_status: ListRulesV1RulesGetEvalStatusType0 | None | Unset = UNSET,
    category: None | str | Unset = UNSET,
    never_fired: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> HTTPValidationError | PageRuleRead | None:
    """ List rules

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        template_type (None | str | Unset):
        enabled (bool | None | Unset):
        has_error (bool | None | Unset): true → only rules whose expression fails
            (eval_status=error); false → the rest. A rule waiting for an input is eval_status=no_data.
        eval_status (ListRulesV1RulesGetEvalStatusType0 | None | Unset): ok | no_data (waiting for
            an input) | error (expression fails).
        category (None | str | Unset): Category of the rule's template (case-insensitive);
            '__none__' = uncategorized.
        never_fired (bool | None | Unset): true → rules that have never fired; false → rules that
            have.
        search (None | str | Unset): Free-text match on name / condition / summary.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageRuleRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
template_type=template_type,
enabled=enabled,
has_error=has_error,
eval_status=eval_status,
category=category,
never_fired=never_fired,
search=search,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    template_type: None | str | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    has_error: bool | None | Unset = UNSET,
    eval_status: ListRulesV1RulesGetEvalStatusType0 | None | Unset = UNSET,
    category: None | str | Unset = UNSET,
    never_fired: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageRuleRead]:
    """ List rules

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        template_type (None | str | Unset):
        enabled (bool | None | Unset):
        has_error (bool | None | Unset): true → only rules whose expression fails
            (eval_status=error); false → the rest. A rule waiting for an input is eval_status=no_data.
        eval_status (ListRulesV1RulesGetEvalStatusType0 | None | Unset): ok | no_data (waiting for
            an input) | error (expression fails).
        category (None | str | Unset): Category of the rule's template (case-insensitive);
            '__none__' = uncategorized.
        never_fired (bool | None | Unset): true → rules that have never fired; false → rules that
            have.
        search (None | str | Unset): Free-text match on name / condition / summary.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageRuleRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
template_type=template_type,
enabled=enabled,
has_error=has_error,
eval_status=eval_status,
category=category,
never_fired=never_fired,
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
    template_type: None | str | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    has_error: bool | None | Unset = UNSET,
    eval_status: ListRulesV1RulesGetEvalStatusType0 | None | Unset = UNSET,
    category: None | str | Unset = UNSET,
    never_fired: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> HTTPValidationError | PageRuleRead | None:
    """ List rules

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        template_type (None | str | Unset):
        enabled (bool | None | Unset):
        has_error (bool | None | Unset): true → only rules whose expression fails
            (eval_status=error); false → the rest. A rule waiting for an input is eval_status=no_data.
        eval_status (ListRulesV1RulesGetEvalStatusType0 | None | Unset): ok | no_data (waiting for
            an input) | error (expression fails).
        category (None | str | Unset): Category of the rule's template (case-insensitive);
            '__none__' = uncategorized.
        never_fired (bool | None | Unset): true → rules that have never fired; false → rules that
            have.
        search (None | str | Unset): Free-text match on name / condition / summary.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageRuleRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
template_type=template_type,
enabled=enabled,
has_error=has_error,
eval_status=eval_status,
category=category,
never_fired=never_fired,
search=search,

    )).parsed
