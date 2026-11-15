from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.apply_import_v1_config_import_apply_post_response_apply_import_v1_config_import_apply_post import ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost
from ...models.http_validation_error import HTTPValidationError
from ...models.import_apply import ImportApply
from typing import cast



def _get_kwargs(
    *,
    body: ImportApply,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/config/import/apply",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ImportApply,

) -> Response[ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost | HTTPValidationError]:
    """ Apply a pack with per-item choices (atomic)

     Applies the pack after the per-item decisions: copies get a `_copy` name (a copied template takes
    the pack's rules / routes / schedules that point to it), skipped and identical items are left out.
    One transaction, audited as `config.import`, then a hot reload.

    Args:
        body (ImportApply):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost | HTTPValidationError]
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
    body: ImportApply,

) -> ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost | HTTPValidationError | None:
    """ Apply a pack with per-item choices (atomic)

     Applies the pack after the per-item decisions: copies get a `_copy` name (a copied template takes
    the pack's rules / routes / schedules that point to it), skipped and identical items are left out.
    One transaction, audited as `config.import`, then a hot reload.

    Args:
        body (ImportApply):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost | HTTPValidationError
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ImportApply,

) -> Response[ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost | HTTPValidationError]:
    """ Apply a pack with per-item choices (atomic)

     Applies the pack after the per-item decisions: copies get a `_copy` name (a copied template takes
    the pack's rules / routes / schedules that point to it), skipped and identical items are left out.
    One transaction, audited as `config.import`, then a hot reload.

    Args:
        body (ImportApply):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost | HTTPValidationError]
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
    body: ImportApply,

) -> ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost | HTTPValidationError | None:
    """ Apply a pack with per-item choices (atomic)

     Applies the pack after the per-item decisions: copies get a `_copy` name (a copied template takes
    the pack's rules / routes / schedules that point to it), skipped and identical items are left out.
    One transaction, audited as `config.import`, then a hot reload.

    Args:
        body (ImportApply):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApplyImportV1ConfigImportApplyPostResponseApplyImportV1ConfigImportApplyPost | HTTPValidationError
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
