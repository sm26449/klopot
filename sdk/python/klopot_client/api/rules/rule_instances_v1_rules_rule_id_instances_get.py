from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.rule_instance_read import RuleInstanceRead
from typing import cast



def _get_kwargs(
    rule_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/rules/{rule_id}/instances".format(rule_id=quote(str(rule_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | list[RuleInstanceRead] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in (_response_200):
            response_200_item = RuleInstanceRead.from_dict(response_200_item_data)



            response_200.append(response_200_item)

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | list[RuleInstanceRead]]:
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

) -> Response[HTTPValidationError | list[RuleInstanceRead]]:
    """ The instances of a rule and their state

     A parametric rule (``for_each``, ADR-0005) runs once per value: each instance has its own run state,
    streak and last message. An ordinary rule has one instance, ``""``.

    Args:
        rule_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[RuleInstanceRead]]
     """


    kwargs = _get_kwargs(
        rule_id=rule_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    rule_id: int,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | list[RuleInstanceRead] | None:
    """ The instances of a rule and their state

     A parametric rule (``for_each``, ADR-0005) runs once per value: each instance has its own run state,
    streak and last message. An ordinary rule has one instance, ``""``.

    Args:
        rule_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[RuleInstanceRead]
     """


    return sync_detailed(
        rule_id=rule_id,
client=client,

    ).parsed

async def asyncio_detailed(
    rule_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | list[RuleInstanceRead]]:
    """ The instances of a rule and their state

     A parametric rule (``for_each``, ADR-0005) runs once per value: each instance has its own run state,
    streak and last message. An ordinary rule has one instance, ``""``.

    Args:
        rule_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[RuleInstanceRead]]
     """


    kwargs = _get_kwargs(
        rule_id=rule_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    rule_id: int,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | list[RuleInstanceRead] | None:
    """ The instances of a rule and their state

     A parametric rule (``for_each``, ADR-0005) runs once per value: each instance has its own run state,
    streak and last message. An ordinary rule has one instance, ``""``.

    Args:
        rule_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[RuleInstanceRead]
     """


    return (await asyncio_detailed(
        rule_id=rule_id,
client=client,

    )).parsed
