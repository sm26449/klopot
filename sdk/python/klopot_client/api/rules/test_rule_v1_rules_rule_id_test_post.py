from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.fire_response import FireResponse
from ...models.http_validation_error import HTTPValidationError
from ...models.test_rule_body import TestRuleBody
from typing import cast



def _get_kwargs(
    rule_id: int,
    *,
    body: TestRuleBody,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/rules/{rule_id}/test".format(rule_id=quote(str(rule_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> FireResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FireResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[FireResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    rule_id: int,
    *,
    client: AuthenticatedClient,
    body: TestRuleBody,

) -> Response[FireResponse | HTTPValidationError]:
    """ Test fire — bypass throttle/quiet, dry-run on mock context

     Fires the rule's template with caller-supplied context. The envelope is marked test=True so throttle
    and quiet hours are skipped (template.enabled and snooze still apply). Useful from the UI to preview
    a rendered title/message.

    Args:
        rule_id (int):
        body (TestRuleBody): ``POST /v1/rules/{id}/test`` body — supply mock context.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FireResponse | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        rule_id=rule_id,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    rule_id: int,
    *,
    client: AuthenticatedClient,
    body: TestRuleBody,

) -> FireResponse | HTTPValidationError | None:
    """ Test fire — bypass throttle/quiet, dry-run on mock context

     Fires the rule's template with caller-supplied context. The envelope is marked test=True so throttle
    and quiet hours are skipped (template.enabled and snooze still apply). Useful from the UI to preview
    a rendered title/message.

    Args:
        rule_id (int):
        body (TestRuleBody): ``POST /v1/rules/{id}/test`` body — supply mock context.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FireResponse | HTTPValidationError
     """


    return sync_detailed(
        rule_id=rule_id,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    rule_id: int,
    *,
    client: AuthenticatedClient,
    body: TestRuleBody,

) -> Response[FireResponse | HTTPValidationError]:
    """ Test fire — bypass throttle/quiet, dry-run on mock context

     Fires the rule's template with caller-supplied context. The envelope is marked test=True so throttle
    and quiet hours are skipped (template.enabled and snooze still apply). Useful from the UI to preview
    a rendered title/message.

    Args:
        rule_id (int):
        body (TestRuleBody): ``POST /v1/rules/{id}/test`` body — supply mock context.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FireResponse | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        rule_id=rule_id,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    rule_id: int,
    *,
    client: AuthenticatedClient,
    body: TestRuleBody,

) -> FireResponse | HTTPValidationError | None:
    """ Test fire — bypass throttle/quiet, dry-run on mock context

     Fires the rule's template with caller-supplied context. The envelope is marked test=True so throttle
    and quiet hours are skipped (template.enabled and snooze still apply). Useful from the UI to preview
    a rendered title/message.

    Args:
        rule_id (int):
        body (TestRuleBody): ``POST /v1/rules/{id}/test`` body — supply mock context.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FireResponse | HTTPValidationError
     """


    return (await asyncio_detailed(
        rule_id=rule_id,
client=client,
body=body,

    )).parsed
