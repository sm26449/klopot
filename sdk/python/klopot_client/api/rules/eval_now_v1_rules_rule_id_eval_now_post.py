from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.eval_rule_result import EvalRuleResult
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    rule_id: int,
    *,
    instance: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    json_instance: None | str | Unset
    if isinstance(instance, Unset):
        json_instance = UNSET
    else:
        json_instance = instance
    params["instance"] = json_instance


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/rules/{rule_id}/eval-now".format(rule_id=quote(str(rule_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> EvalRuleResult | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = EvalRuleResult.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[EvalRuleResult | HTTPValidationError]:
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
    instance: None | str | Unset = UNSET,

) -> Response[EvalRuleResult | HTTPValidationError]:
    """ Force evaluate rule against current state cache (no fire)

     Builds the rule's context from the live state cache, runs the condition expression once, and returns
    the outcome. Does NOT increment persist counters or dispatch — diagnostic only.

    Args:
        rule_id (int):
        instance (None | str | Unset): The instance of a parametric rule (default: the first)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EvalRuleResult | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        rule_id=rule_id,
instance=instance,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    rule_id: int,
    *,
    client: AuthenticatedClient,
    instance: None | str | Unset = UNSET,

) -> EvalRuleResult | HTTPValidationError | None:
    """ Force evaluate rule against current state cache (no fire)

     Builds the rule's context from the live state cache, runs the condition expression once, and returns
    the outcome. Does NOT increment persist counters or dispatch — diagnostic only.

    Args:
        rule_id (int):
        instance (None | str | Unset): The instance of a parametric rule (default: the first)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EvalRuleResult | HTTPValidationError
     """


    return sync_detailed(
        rule_id=rule_id,
client=client,
instance=instance,

    ).parsed

async def asyncio_detailed(
    rule_id: int,
    *,
    client: AuthenticatedClient,
    instance: None | str | Unset = UNSET,

) -> Response[EvalRuleResult | HTTPValidationError]:
    """ Force evaluate rule against current state cache (no fire)

     Builds the rule's context from the live state cache, runs the condition expression once, and returns
    the outcome. Does NOT increment persist counters or dispatch — diagnostic only.

    Args:
        rule_id (int):
        instance (None | str | Unset): The instance of a parametric rule (default: the first)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EvalRuleResult | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        rule_id=rule_id,
instance=instance,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    rule_id: int,
    *,
    client: AuthenticatedClient,
    instance: None | str | Unset = UNSET,

) -> EvalRuleResult | HTTPValidationError | None:
    """ Force evaluate rule against current state cache (no fire)

     Builds the rule's context from the live state cache, runs the condition expression once, and returns
    the outcome. Does NOT increment persist counters or dispatch — diagnostic only.

    Args:
        rule_id (int):
        instance (None | str | Unset): The instance of a parametric rule (default: the first)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EvalRuleResult | HTTPValidationError
     """


    return (await asyncio_detailed(
        rule_id=rule_id,
client=client,
instance=instance,

    )).parsed
