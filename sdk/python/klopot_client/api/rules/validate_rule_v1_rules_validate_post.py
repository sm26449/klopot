from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.validate_rule_body import ValidateRuleBody
from ...models.validate_rule_result import ValidateRuleResult
from typing import cast



def _get_kwargs(
    *,
    body: ValidateRuleBody,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/rules/validate",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | ValidateRuleResult | None:
    if response.status_code == 200:
        response_200 = ValidateRuleResult.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | ValidateRuleResult]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ValidateRuleBody,

) -> Response[HTTPValidationError | ValidateRuleResult]:
    """ Parse + check a condition expression (no rule, no side effects)

     Evaluates the expression against the live state cache so the UI editor can show whether it parses,
    which variables it references (with their current value / age / staleness) and which names are
    unknown. Does not create or modify any rule.

    Args:
        body (ValidateRuleBody): ``POST /v1/rules/validate`` body.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ValidateRuleResult]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    body: ValidateRuleBody,

) -> HTTPValidationError | ValidateRuleResult | None:
    """ Parse + check a condition expression (no rule, no side effects)

     Evaluates the expression against the live state cache so the UI editor can show whether it parses,
    which variables it references (with their current value / age / staleness) and which names are
    unknown. Does not create or modify any rule.

    Args:
        body (ValidateRuleBody): ``POST /v1/rules/validate`` body.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ValidateRuleResult
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ValidateRuleBody,

) -> Response[HTTPValidationError | ValidateRuleResult]:
    """ Parse + check a condition expression (no rule, no side effects)

     Evaluates the expression against the live state cache so the UI editor can show whether it parses,
    which variables it references (with their current value / age / staleness) and which names are
    unknown. Does not create or modify any rule.

    Args:
        body (ValidateRuleBody): ``POST /v1/rules/validate`` body.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ValidateRuleResult]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    body: ValidateRuleBody,

) -> HTTPValidationError | ValidateRuleResult | None:
    """ Parse + check a condition expression (no rule, no side effects)

     Evaluates the expression against the live state cache so the UI editor can show whether it parses,
    which variables it references (with their current value / age / staleness) and which names are
    unknown. Does not create or modify any rule.

    Args:
        body (ValidateRuleBody): ``POST /v1/rules/validate`` body.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ValidateRuleResult
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
