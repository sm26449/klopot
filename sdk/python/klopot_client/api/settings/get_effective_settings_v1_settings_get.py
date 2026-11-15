from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.get_effective_settings_v1_settings_get_response_get_effective_settings_v1_settings_get import GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet
from typing import cast



def _get_kwargs(
    
) -> dict[str, Any]:
    

    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/settings",
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet | None:
    if response.status_code == 200:
        response_200 = GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet.from_dict(response.json())



        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet]:
    """ Effective runtime settings (read-only)

     The values the service actually runs with, sourced from the environment. Each item is marked
    read_only=true and tagged with its source (env/default). No PATCH in v1 (see audit H-6).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet]
     """


    kwargs = _get_kwargs(
        
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,

) -> GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet | None:
    """ Effective runtime settings (read-only)

     The values the service actually runs with, sourced from the environment. Each item is marked
    read_only=true and tagged with its source (env/default). No PATCH in v1 (see audit H-6).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet
     """


    return sync_detailed(
        client=client,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,

) -> Response[GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet]:
    """ Effective runtime settings (read-only)

     The values the service actually runs with, sourced from the environment. Each item is marked
    read_only=true and tagged with its source (env/default). No PATCH in v1 (see audit H-6).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet]
     """


    kwargs = _get_kwargs(
        
    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,

) -> GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet | None:
    """ Effective runtime settings (read-only)

     The values the service actually runs with, sourced from the environment. Each item is marked
    read_only=true and tagged with its source (env/default). No PATCH in v1 (see audit H-6).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetEffectiveSettingsV1SettingsGetResponseGetEffectiveSettingsV1SettingsGet
     """


    return (await asyncio_detailed(
        client=client,

    )).parsed
