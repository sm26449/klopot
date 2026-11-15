from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.activity_rule_create import ActivityRuleCreate
from ...models.http_validation_error import HTTPValidationError
from ...models.rule_preview import RulePreview
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    body: ActivityRuleCreate,
    hours: int | Unset = 24,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    params: dict[str, Any] = {}

    params["hours"] = hours


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/activity/rules/preview",
        "params": params,
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | RulePreview | None:
    if response.status_code == 200:
        response_200 = RulePreview.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | RulePreview]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ActivityRuleCreate,
    hours: int | Unset = 24,

) -> Response[HTTPValidationError | RulePreview]:
    """ How many recent requests a rule would match

    Args:
        hours (int | Unset):  Default: 24.
        body (ActivityRuleCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RulePreview]
     """


    kwargs = _get_kwargs(
        body=body,
hours=hours,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    body: ActivityRuleCreate,
    hours: int | Unset = 24,

) -> HTTPValidationError | RulePreview | None:
    """ How many recent requests a rule would match

    Args:
        hours (int | Unset):  Default: 24.
        body (ActivityRuleCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RulePreview
     """


    return sync_detailed(
        client=client,
body=body,
hours=hours,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ActivityRuleCreate,
    hours: int | Unset = 24,

) -> Response[HTTPValidationError | RulePreview]:
    """ How many recent requests a rule would match

    Args:
        hours (int | Unset):  Default: 24.
        body (ActivityRuleCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RulePreview]
     """


    kwargs = _get_kwargs(
        body=body,
hours=hours,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    body: ActivityRuleCreate,
    hours: int | Unset = 24,

) -> HTTPValidationError | RulePreview | None:
    """ How many recent requests a rule would match

    Args:
        hours (int | Unset):  Default: 24.
        body (ActivityRuleCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RulePreview
     """


    return (await asyncio_detailed(
        client=client,
body=body,
hours=hours,

    )).parsed
