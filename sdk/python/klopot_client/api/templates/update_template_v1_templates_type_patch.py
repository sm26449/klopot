from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.template_read import TemplateRead
from ...models.template_update import TemplateUpdate
from typing import cast



def _get_kwargs(
    type_: str,
    *,
    body: TemplateUpdate,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/v1/templates/{type_}".format(type_=quote(str(type_), safe=""),),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | TemplateRead | None:
    if response.status_code == 200:
        response_200 = TemplateRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | TemplateRead]:
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
    body: TemplateUpdate,

) -> Response[HTTPValidationError | TemplateRead]:
    """ Update template

    Args:
        type_ (str):
        body (TemplateUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TemplateRead]
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
    body: TemplateUpdate,

) -> HTTPValidationError | TemplateRead | None:
    """ Update template

    Args:
        type_ (str):
        body (TemplateUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TemplateRead
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
    body: TemplateUpdate,

) -> Response[HTTPValidationError | TemplateRead]:
    """ Update template

    Args:
        type_ (str):
        body (TemplateUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TemplateRead]
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
    body: TemplateUpdate,

) -> HTTPValidationError | TemplateRead | None:
    """ Update template

    Args:
        type_ (str):
        body (TemplateUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TemplateRead
     """


    return (await asyncio_detailed(
        type_=type_,
client=client,
body=body,

    )).parsed
