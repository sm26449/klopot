from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.preview_template_v1_templates_type_preview_post_body_type_0 import PreviewTemplateV1TemplatesTypePreviewPostBodyType0
from ...models.preview_template_v1_templates_type_preview_post_response_preview_template_v1_templates_type_preview_post import PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    type_: str,
    *,
    body: None | PreviewTemplateV1TemplatesTypePreviewPostBodyType0 | Unset = UNSET,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/templates/{type_}/preview".format(type_=quote(str(type_), safe=""),),
    }

    
    if isinstance(body, PreviewTemplateV1TemplatesTypePreviewPostBodyType0):
        _kwargs["json"] = body.to_dict()
    else:
        _kwargs["json"] = body

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost | None:
    if response.status_code == 200:
        response_200 = PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    type_: str,
    *,
    client: AuthenticatedClient,
    body: None | PreviewTemplateV1TemplatesTypePreviewPostBodyType0 | Unset = UNSET,

) -> Response[HTTPValidationError | PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost]:
    """ Render a template against a supplied context (no dispatch, no log)

     Renders title + message with the given context. Placeholders that don't resolve are reported in
    ``missing_vars`` (and appear as ``[?name]`` in the rendered output). Pure function — nothing is
    dispatched or logged.

    Args:
        type_ (str):
        body (None | PreviewTemplateV1TemplatesTypePreviewPostBodyType0 | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost]
     """


    kwargs = _get_kwargs(
        type_=type_,
body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    type_: str,
    *,
    client: AuthenticatedClient,
    body: None | PreviewTemplateV1TemplatesTypePreviewPostBodyType0 | Unset = UNSET,

) -> HTTPValidationError | PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost | None:
    """ Render a template against a supplied context (no dispatch, no log)

     Renders title + message with the given context. Placeholders that don't resolve are reported in
    ``missing_vars`` (and appear as ``[?name]`` in the rendered output). Pure function — nothing is
    dispatched or logged.

    Args:
        type_ (str):
        body (None | PreviewTemplateV1TemplatesTypePreviewPostBodyType0 | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost
     """


    return sync_detailed(
        type_=type_,
client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    type_: str,
    *,
    client: AuthenticatedClient,
    body: None | PreviewTemplateV1TemplatesTypePreviewPostBodyType0 | Unset = UNSET,

) -> Response[HTTPValidationError | PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost]:
    """ Render a template against a supplied context (no dispatch, no log)

     Renders title + message with the given context. Placeholders that don't resolve are reported in
    ``missing_vars`` (and appear as ``[?name]`` in the rendered output). Pure function — nothing is
    dispatched or logged.

    Args:
        type_ (str):
        body (None | PreviewTemplateV1TemplatesTypePreviewPostBodyType0 | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost]
     """


    kwargs = _get_kwargs(
        type_=type_,
body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    type_: str,
    *,
    client: AuthenticatedClient,
    body: None | PreviewTemplateV1TemplatesTypePreviewPostBodyType0 | Unset = UNSET,

) -> HTTPValidationError | PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost | None:
    """ Render a template against a supplied context (no dispatch, no log)

     Renders title + message with the given context. Placeholders that don't resolve are reported in
    ``missing_vars`` (and appear as ``[?name]`` in the rendered output). Pure function — nothing is
    dispatched or logged.

    Args:
        type_ (str):
        body (None | PreviewTemplateV1TemplatesTypePreviewPostBodyType0 | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PreviewTemplateV1TemplatesTypePreviewPostResponsePreviewTemplateV1TemplatesTypePreviewPost
     """


    return (await asyncio_detailed(
        type_=type_,
client=client,
body=body,

    )).parsed
