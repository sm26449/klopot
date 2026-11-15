from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.restart_input_v1_inputs_input_id_restart_post_response_restart_input_v1_inputs_input_id_restart_post import RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost
from typing import cast



def _get_kwargs(
    input_id: int,

) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/inputs/{input_id}/restart".format(input_id=quote(str(input_id), safe=""),),
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost | None:
    if response.status_code == 200:
        response_200 = RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    input_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost]:
    """ Force restart of an adapter

    Args:
        input_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost]
     """


    kwargs = _get_kwargs(
        input_id=input_id,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    input_id: int,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost | None:
    """ Force restart of an adapter

    Args:
        input_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost
     """


    return sync_detailed(
        input_id=input_id,
client=client,

    ).parsed

async def asyncio_detailed(
    input_id: int,
    *,
    client: AuthenticatedClient,

) -> Response[HTTPValidationError | RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost]:
    """ Force restart of an adapter

    Args:
        input_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost]
     """


    kwargs = _get_kwargs(
        input_id=input_id,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    input_id: int,
    *,
    client: AuthenticatedClient,

) -> HTTPValidationError | RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost | None:
    """ Force restart of an adapter

    Args:
        input_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RestartInputV1InputsInputIdRestartPostResponseRestartInputV1InputsInputIdRestartPost
     """


    return (await asyncio_detailed(
        input_id=input_id,
client=client,

    )).parsed
