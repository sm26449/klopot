from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.receive_webhook_v1_inputs_input_id_webhook_post_response_receive_webhook_v1_inputs_input_id_webhook_post import ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    input_id: int,
    *,
    x_input_token: None | str | Unset = UNSET,
    authorization: None | str | Unset = UNSET,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_input_token, Unset):
        headers["X-Input-Token"] = x_input_token

    if not isinstance(authorization, Unset):
        headers["authorization"] = authorization



    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/inputs/{input_id}/webhook".format(input_id=quote(str(input_id), safe=""),),
    }


    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost | None:
    if response.status_code == 202:
        response_202 = ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost.from_dict(response.json())



        return response_202

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    input_id: int,
    *,
    client: AuthenticatedClient | Client,
    x_input_token: None | str | Unset = UNSET,
    authorization: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost]:
    """ Receive a webhook payload for this input

     Public endpoint where external systems POST values. The input declares whether auth is required and
    which env var holds the expected token. Bypasses the normal X-API-Key auth so external services can
    post without a full alertd credential — they only need the per-input token.

    Args:
        input_id (int):
        x_input_token (None | str | Unset):
        authorization (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost]
     """


    kwargs = _get_kwargs(
        input_id=input_id,
x_input_token=x_input_token,
authorization=authorization,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    input_id: int,
    *,
    client: AuthenticatedClient | Client,
    x_input_token: None | str | Unset = UNSET,
    authorization: None | str | Unset = UNSET,

) -> HTTPValidationError | ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost | None:
    """ Receive a webhook payload for this input

     Public endpoint where external systems POST values. The input declares whether auth is required and
    which env var holds the expected token. Bypasses the normal X-API-Key auth so external services can
    post without a full alertd credential — they only need the per-input token.

    Args:
        input_id (int):
        x_input_token (None | str | Unset):
        authorization (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost
     """


    return sync_detailed(
        input_id=input_id,
client=client,
x_input_token=x_input_token,
authorization=authorization,

    ).parsed

async def asyncio_detailed(
    input_id: int,
    *,
    client: AuthenticatedClient | Client,
    x_input_token: None | str | Unset = UNSET,
    authorization: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost]:
    """ Receive a webhook payload for this input

     Public endpoint where external systems POST values. The input declares whether auth is required and
    which env var holds the expected token. Bypasses the normal X-API-Key auth so external services can
    post without a full alertd credential — they only need the per-input token.

    Args:
        input_id (int):
        x_input_token (None | str | Unset):
        authorization (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost]
     """


    kwargs = _get_kwargs(
        input_id=input_id,
x_input_token=x_input_token,
authorization=authorization,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    input_id: int,
    *,
    client: AuthenticatedClient | Client,
    x_input_token: None | str | Unset = UNSET,
    authorization: None | str | Unset = UNSET,

) -> HTTPValidationError | ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost | None:
    """ Receive a webhook payload for this input

     Public endpoint where external systems POST values. The input declares whether auth is required and
    which env var holds the expected token. Bypasses the normal X-API-Key auth so external services can
    post without a full alertd credential — they only need the per-input token.

    Args:
        input_id (int):
        x_input_token (None | str | Unset):
        authorization (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ReceiveWebhookV1InputsInputIdWebhookPostResponseReceiveWebhookV1InputsInputIdWebhookPost
     """


    return (await asyncio_detailed(
        input_id=input_id,
client=client,
x_input_token=x_input_token,
authorization=authorization,

    )).parsed
