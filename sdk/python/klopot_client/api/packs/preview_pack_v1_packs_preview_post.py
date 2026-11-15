from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.pack_source import PackSource
from ...models.preview_pack_v1_packs_preview_post_response_preview_pack_v1_packs_preview_post import PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost
from typing import cast



def _get_kwargs(
    *,
    body: PackSource,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/packs/preview",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost | None:
    if response.status_code == 200:
        response_200 = PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: PackSource,

) -> Response[HTTPValidationError | PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost]:
    """ Preview installing a pack

     Substitutes the parameters, then classifies every item as `new`, `identical` or `differs` against
    the live configuration, like /v1/config/import/preview. Writes nothing.

    Args:
        body (PackSource):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost]
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
    body: PackSource,

) -> HTTPValidationError | PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost | None:
    """ Preview installing a pack

     Substitutes the parameters, then classifies every item as `new`, `identical` or `differs` against
    the live configuration, like /v1/config/import/preview. Writes nothing.

    Args:
        body (PackSource):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: PackSource,

) -> Response[HTTPValidationError | PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost]:
    """ Preview installing a pack

     Substitutes the parameters, then classifies every item as `new`, `identical` or `differs` against
    the live configuration, like /v1/config/import/preview. Writes nothing.

    Args:
        body (PackSource):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost]
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
    body: PackSource,

) -> HTTPValidationError | PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost | None:
    """ Preview installing a pack

     Substitutes the parameters, then classifies every item as `new`, `identical` or `differs` against
    the live configuration, like /v1/config/import/preview. Writes nothing.

    Args:
        body (PackSource):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PreviewPackV1PacksPreviewPostResponsePreviewPackV1PacksPreviewPost
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
