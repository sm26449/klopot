from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.rule_transition_read import RuleTransitionRead
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    rule_id: int,
    *,
    limit: int | Unset = 100,
    instance: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["limit"] = limit

    json_instance: None | str | Unset
    if isinstance(instance, Unset):
        json_instance = UNSET
    else:
        json_instance = instance
    params["instance"] = json_instance


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/rules/{rule_id}/transitions".format(rule_id=quote(str(rule_id), safe=""),),
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | list[RuleTransitionRead] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in (_response_200):
            response_200_item = RuleTransitionRead.from_dict(response_200_item_data)



            response_200.append(response_200_item)

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | list[RuleTransitionRead]]:
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
    limit: int | Unset = 100,
    instance: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | list[RuleTransitionRead]]:
    """ Run-state history of a rule, newest first

     One entry per change of the rule's run state (inactive, pending, firing, no_data, error), never per
    evaluation. Kept as long as the log (ALERTD_LOG_RETENTION_DAYS); a flapping rule records at most 60
    changes an hour, and the next entry's detail says how many were skipped.

    Args:
        rule_id (int):
        limit (int | Unset):  Default: 100.
        instance (None | str | Unset): Only this instance of a parametric rule

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[RuleTransitionRead]]
     """


    kwargs = _get_kwargs(
        rule_id=rule_id,
limit=limit,
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
    limit: int | Unset = 100,
    instance: None | str | Unset = UNSET,

) -> HTTPValidationError | list[RuleTransitionRead] | None:
    """ Run-state history of a rule, newest first

     One entry per change of the rule's run state (inactive, pending, firing, no_data, error), never per
    evaluation. Kept as long as the log (ALERTD_LOG_RETENTION_DAYS); a flapping rule records at most 60
    changes an hour, and the next entry's detail says how many were skipped.

    Args:
        rule_id (int):
        limit (int | Unset):  Default: 100.
        instance (None | str | Unset): Only this instance of a parametric rule

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[RuleTransitionRead]
     """


    return sync_detailed(
        rule_id=rule_id,
client=client,
limit=limit,
instance=instance,

    ).parsed

async def asyncio_detailed(
    rule_id: int,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 100,
    instance: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | list[RuleTransitionRead]]:
    """ Run-state history of a rule, newest first

     One entry per change of the rule's run state (inactive, pending, firing, no_data, error), never per
    evaluation. Kept as long as the log (ALERTD_LOG_RETENTION_DAYS); a flapping rule records at most 60
    changes an hour, and the next entry's detail says how many were skipped.

    Args:
        rule_id (int):
        limit (int | Unset):  Default: 100.
        instance (None | str | Unset): Only this instance of a parametric rule

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[RuleTransitionRead]]
     """


    kwargs = _get_kwargs(
        rule_id=rule_id,
limit=limit,
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
    limit: int | Unset = 100,
    instance: None | str | Unset = UNSET,

) -> HTTPValidationError | list[RuleTransitionRead] | None:
    """ Run-state history of a rule, newest first

     One entry per change of the rule's run state (inactive, pending, firing, no_data, error), never per
    evaluation. Kept as long as the log (ALERTD_LOG_RETENTION_DAYS); a flapping rule records at most 60
    changes an hour, and the next entry's detail says how many were skipped.

    Args:
        rule_id (int):
        limit (int | Unset):  Default: 100.
        instance (None | str | Unset): Only this instance of a parametric rule

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[RuleTransitionRead]
     """


    return (await asyncio_detailed(
        rule_id=rule_id,
client=client,
limit=limit,
instance=instance,

    )).parsed
