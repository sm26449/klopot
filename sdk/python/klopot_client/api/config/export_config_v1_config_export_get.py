from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    mask_secrets: bool | Unset = False,
    sections: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    names: None | str | Unset = UNSET,
    with_dependencies: bool | Unset = False,
    pack_id: None | str | Unset = UNSET,
    pack_name: None | str | Unset = UNSET,
    pack_description: None | str | Unset = UNSET,
    pack_version: str | Unset = '1.0.0',

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["mask_secrets"] = mask_secrets

    json_sections: None | str | Unset
    if isinstance(sections, Unset):
        json_sections = UNSET
    else:
        json_sections = sections
    params["sections"] = json_sections

    json_category: None | str | Unset
    if isinstance(category, Unset):
        json_category = UNSET
    else:
        json_category = category
    params["category"] = json_category

    json_names: None | str | Unset
    if isinstance(names, Unset):
        json_names = UNSET
    else:
        json_names = names
    params["names"] = json_names

    params["with_dependencies"] = with_dependencies

    json_pack_id: None | str | Unset
    if isinstance(pack_id, Unset):
        json_pack_id = UNSET
    else:
        json_pack_id = pack_id
    params["pack_id"] = json_pack_id

    json_pack_name: None | str | Unset
    if isinstance(pack_name, Unset):
        json_pack_name = UNSET
    else:
        json_pack_name = pack_name
    params["pack_name"] = json_pack_name

    json_pack_description: None | str | Unset
    if isinstance(pack_description, Unset):
        json_pack_description = UNSET
    else:
        json_pack_description = pack_description
    params["pack_description"] = json_pack_description

    params["pack_version"] = pack_version


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/config/export",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    mask_secrets: bool | Unset = False,
    sections: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    names: None | str | Unset = UNSET,
    with_dependencies: bool | Unset = False,
    pack_id: None | str | Unset = UNSET,
    pack_name: None | str | Unset = UNSET,
    pack_description: None | str | Unset = UNSET,
    pack_version: str | Unset = '1.0.0',

) -> Response[Any | HTTPValidationError]:
    """ Export full configuration as YAML

     Returns every config table (inputs, variables, templates, channels, routes, rules, schedules,
    settings) as a portable YAML document. Identifiers across sections use NAMES, not auto-generated ids
    — safe to apply on a different deployment.

    Set `?mask_secrets=true` to rewrite literal-looking secrets (bot_token, password, api_key fields) as
    `env:UNKNOWN_*` placeholders so the YAML is shareable.

    Args:
        mask_secrets (bool | Unset):  Default: False.
        sections (None | str | Unset): Comma-separated subset: inputs, templates, channels,
            variables, rules, routes, schedules. Selecting templates includes their routes. Omit for
            everything.
        category (None | str | Unset): Keep templates of this category and rules whose template is
            in it (case-insensitive; '__none__' = uncategorized).
        names (None | str | Unset): Comma-separated identifiers to keep (template type, rule /
            variable name…).
        with_dependencies (bool | Unset): Close the selection over what it needs: templates,
            variables, inputs, inhibiting rules, gate variables, channels of its routes
            (docs/PACKS.md). Default: False.
        pack_id (None | str | Unset): Export as a pack: adds a `pack:` header with this id
            (secrets are always masked then).
        pack_name (None | str | Unset): Pack name (default: the id).
        pack_description (None | str | Unset):
        pack_version (str | Unset):  Default: '1.0.0'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        mask_secrets=mask_secrets,
sections=sections,
category=category,
names=names,
with_dependencies=with_dependencies,
pack_id=pack_id,
pack_name=pack_name,
pack_description=pack_description,
pack_version=pack_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    mask_secrets: bool | Unset = False,
    sections: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    names: None | str | Unset = UNSET,
    with_dependencies: bool | Unset = False,
    pack_id: None | str | Unset = UNSET,
    pack_name: None | str | Unset = UNSET,
    pack_description: None | str | Unset = UNSET,
    pack_version: str | Unset = '1.0.0',

) -> Any | HTTPValidationError | None:
    """ Export full configuration as YAML

     Returns every config table (inputs, variables, templates, channels, routes, rules, schedules,
    settings) as a portable YAML document. Identifiers across sections use NAMES, not auto-generated ids
    — safe to apply on a different deployment.

    Set `?mask_secrets=true` to rewrite literal-looking secrets (bot_token, password, api_key fields) as
    `env:UNKNOWN_*` placeholders so the YAML is shareable.

    Args:
        mask_secrets (bool | Unset):  Default: False.
        sections (None | str | Unset): Comma-separated subset: inputs, templates, channels,
            variables, rules, routes, schedules. Selecting templates includes their routes. Omit for
            everything.
        category (None | str | Unset): Keep templates of this category and rules whose template is
            in it (case-insensitive; '__none__' = uncategorized).
        names (None | str | Unset): Comma-separated identifiers to keep (template type, rule /
            variable name…).
        with_dependencies (bool | Unset): Close the selection over what it needs: templates,
            variables, inputs, inhibiting rules, gate variables, channels of its routes
            (docs/PACKS.md). Default: False.
        pack_id (None | str | Unset): Export as a pack: adds a `pack:` header with this id
            (secrets are always masked then).
        pack_name (None | str | Unset): Pack name (default: the id).
        pack_description (None | str | Unset):
        pack_version (str | Unset):  Default: '1.0.0'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return sync_detailed(
        client=client,
mask_secrets=mask_secrets,
sections=sections,
category=category,
names=names,
with_dependencies=with_dependencies,
pack_id=pack_id,
pack_name=pack_name,
pack_description=pack_description,
pack_version=pack_version,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    mask_secrets: bool | Unset = False,
    sections: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    names: None | str | Unset = UNSET,
    with_dependencies: bool | Unset = False,
    pack_id: None | str | Unset = UNSET,
    pack_name: None | str | Unset = UNSET,
    pack_description: None | str | Unset = UNSET,
    pack_version: str | Unset = '1.0.0',

) -> Response[Any | HTTPValidationError]:
    """ Export full configuration as YAML

     Returns every config table (inputs, variables, templates, channels, routes, rules, schedules,
    settings) as a portable YAML document. Identifiers across sections use NAMES, not auto-generated ids
    — safe to apply on a different deployment.

    Set `?mask_secrets=true` to rewrite literal-looking secrets (bot_token, password, api_key fields) as
    `env:UNKNOWN_*` placeholders so the YAML is shareable.

    Args:
        mask_secrets (bool | Unset):  Default: False.
        sections (None | str | Unset): Comma-separated subset: inputs, templates, channels,
            variables, rules, routes, schedules. Selecting templates includes their routes. Omit for
            everything.
        category (None | str | Unset): Keep templates of this category and rules whose template is
            in it (case-insensitive; '__none__' = uncategorized).
        names (None | str | Unset): Comma-separated identifiers to keep (template type, rule /
            variable name…).
        with_dependencies (bool | Unset): Close the selection over what it needs: templates,
            variables, inputs, inhibiting rules, gate variables, channels of its routes
            (docs/PACKS.md). Default: False.
        pack_id (None | str | Unset): Export as a pack: adds a `pack:` header with this id
            (secrets are always masked then).
        pack_name (None | str | Unset): Pack name (default: the id).
        pack_description (None | str | Unset):
        pack_version (str | Unset):  Default: '1.0.0'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        mask_secrets=mask_secrets,
sections=sections,
category=category,
names=names,
with_dependencies=with_dependencies,
pack_id=pack_id,
pack_name=pack_name,
pack_description=pack_description,
pack_version=pack_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    mask_secrets: bool | Unset = False,
    sections: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    names: None | str | Unset = UNSET,
    with_dependencies: bool | Unset = False,
    pack_id: None | str | Unset = UNSET,
    pack_name: None | str | Unset = UNSET,
    pack_description: None | str | Unset = UNSET,
    pack_version: str | Unset = '1.0.0',

) -> Any | HTTPValidationError | None:
    """ Export full configuration as YAML

     Returns every config table (inputs, variables, templates, channels, routes, rules, schedules,
    settings) as a portable YAML document. Identifiers across sections use NAMES, not auto-generated ids
    — safe to apply on a different deployment.

    Set `?mask_secrets=true` to rewrite literal-looking secrets (bot_token, password, api_key fields) as
    `env:UNKNOWN_*` placeholders so the YAML is shareable.

    Args:
        mask_secrets (bool | Unset):  Default: False.
        sections (None | str | Unset): Comma-separated subset: inputs, templates, channels,
            variables, rules, routes, schedules. Selecting templates includes their routes. Omit for
            everything.
        category (None | str | Unset): Keep templates of this category and rules whose template is
            in it (case-insensitive; '__none__' = uncategorized).
        names (None | str | Unset): Comma-separated identifiers to keep (template type, rule /
            variable name…).
        with_dependencies (bool | Unset): Close the selection over what it needs: templates,
            variables, inputs, inhibiting rules, gate variables, channels of its routes
            (docs/PACKS.md). Default: False.
        pack_id (None | str | Unset): Export as a pack: adds a `pack:` header with this id
            (secrets are always masked then).
        pack_name (None | str | Unset): Pack name (default: the id).
        pack_description (None | str | Unset):
        pack_version (str | Unset):  Default: '1.0.0'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return (await asyncio_detailed(
        client=client,
mask_secrets=mask_secrets,
sections=sections,
category=category,
names=names,
with_dependencies=with_dependencies,
pack_id=pack_id,
pack_name=pack_name,
pack_description=pack_description,
pack_version=pack_version,

    )).parsed
