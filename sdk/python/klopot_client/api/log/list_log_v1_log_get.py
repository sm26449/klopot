from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.page_log_entry_read import PageLogEntryRead
from ...models.severity import Severity
from ...types import UNSET, Unset
from typing import cast
import datetime



def _get_kwargs(
    *,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    type_: None | str | Unset = UNSET,
    severity: None | Severity | Unset = UNSET,
    suppressed: bool | None | Unset = UNSET,
    delivery_status: None | str | Unset = UNSET,
    rule_id: int | None | Unset = UNSET,
    incident_id: None | str | Unset = UNSET,
    acknowledged: bool | None | Unset = UNSET,
    is_test: bool | None | Unset = UNSET,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> dict[str, Any]:
    

    

    params: dict[str, Any] = {}

    params["skip"] = skip

    params["limit"] = limit

    json_type_: None | str | Unset
    if isinstance(type_, Unset):
        json_type_ = UNSET
    else:
        json_type_ = type_
    params["type"] = json_type_

    json_severity: None | str | Unset
    if isinstance(severity, Unset):
        json_severity = UNSET
    elif isinstance(severity, Severity):
        json_severity = severity.value
    else:
        json_severity = severity
    params["severity"] = json_severity

    json_suppressed: bool | None | Unset
    if isinstance(suppressed, Unset):
        json_suppressed = UNSET
    else:
        json_suppressed = suppressed
    params["suppressed"] = json_suppressed

    json_delivery_status: None | str | Unset
    if isinstance(delivery_status, Unset):
        json_delivery_status = UNSET
    else:
        json_delivery_status = delivery_status
    params["delivery_status"] = json_delivery_status

    json_rule_id: int | None | Unset
    if isinstance(rule_id, Unset):
        json_rule_id = UNSET
    else:
        json_rule_id = rule_id
    params["rule_id"] = json_rule_id

    json_incident_id: None | str | Unset
    if isinstance(incident_id, Unset):
        json_incident_id = UNSET
    else:
        json_incident_id = incident_id
    params["incident_id"] = json_incident_id

    json_acknowledged: bool | None | Unset
    if isinstance(acknowledged, Unset):
        json_acknowledged = UNSET
    else:
        json_acknowledged = acknowledged
    params["acknowledged"] = json_acknowledged

    json_is_test: bool | None | Unset
    if isinstance(is_test, Unset):
        json_is_test = UNSET
    else:
        json_is_test = is_test
    params["is_test"] = json_is_test

    json_from_: None | str | Unset
    if isinstance(from_, Unset):
        json_from_ = UNSET
    elif isinstance(from_, datetime.datetime):
        json_from_ = from_.isoformat()
    else:
        json_from_ = from_
    params["from"] = json_from_

    json_to: None | str | Unset
    if isinstance(to, Unset):
        json_to = UNSET
    elif isinstance(to, datetime.datetime):
        json_to = to.isoformat()
    else:
        json_to = to
    params["to"] = json_to

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/log",
        "params": params,
    }


    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | PageLogEntryRead | None:
    if response.status_code == 200:
        response_200 = PageLogEntryRead.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | PageLogEntryRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    type_: None | str | Unset = UNSET,
    severity: None | Severity | Unset = UNSET,
    suppressed: bool | None | Unset = UNSET,
    delivery_status: None | str | Unset = UNSET,
    rule_id: int | None | Unset = UNSET,
    incident_id: None | str | Unset = UNSET,
    acknowledged: bool | None | Unset = UNSET,
    is_test: bool | None | Unset = UNSET,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageLogEntryRead]:
    """ Query notification log

     Paged log query. Filters: type, severity, suppressed (true/false), rule_id, time range (from/to
    ISO8601), free-text search on title.

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        type_ (None | str | Unset):
        severity (None | Severity | Unset):
        suppressed (bool | None | Unset): true → only suppressed; false → only dispatched; omit →
            all
        delivery_status (None | str | Unset): Exact settled outcome: sent | partial | failed |
            suppressed.
        rule_id (int | None | Unset):
        incident_id (None | str | Unset):
        acknowledged (bool | None | Unset):
        is_test (bool | None | Unset): true → only test fires; false → only real.
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):
        search (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageLogEntryRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
type_=type_,
severity=severity,
suppressed=suppressed,
delivery_status=delivery_status,
rule_id=rule_id,
incident_id=incident_id,
acknowledged=acknowledged,
is_test=is_test,
from_=from_,
to=to,
search=search,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    type_: None | str | Unset = UNSET,
    severity: None | Severity | Unset = UNSET,
    suppressed: bool | None | Unset = UNSET,
    delivery_status: None | str | Unset = UNSET,
    rule_id: int | None | Unset = UNSET,
    incident_id: None | str | Unset = UNSET,
    acknowledged: bool | None | Unset = UNSET,
    is_test: bool | None | Unset = UNSET,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> HTTPValidationError | PageLogEntryRead | None:
    """ Query notification log

     Paged log query. Filters: type, severity, suppressed (true/false), rule_id, time range (from/to
    ISO8601), free-text search on title.

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        type_ (None | str | Unset):
        severity (None | Severity | Unset):
        suppressed (bool | None | Unset): true → only suppressed; false → only dispatched; omit →
            all
        delivery_status (None | str | Unset): Exact settled outcome: sent | partial | failed |
            suppressed.
        rule_id (int | None | Unset):
        incident_id (None | str | Unset):
        acknowledged (bool | None | Unset):
        is_test (bool | None | Unset): true → only test fires; false → only real.
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):
        search (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageLogEntryRead
     """


    return sync_detailed(
        client=client,
skip=skip,
limit=limit,
type_=type_,
severity=severity,
suppressed=suppressed,
delivery_status=delivery_status,
rule_id=rule_id,
incident_id=incident_id,
acknowledged=acknowledged,
is_test=is_test,
from_=from_,
to=to,
search=search,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    type_: None | str | Unset = UNSET,
    severity: None | Severity | Unset = UNSET,
    suppressed: bool | None | Unset = UNSET,
    delivery_status: None | str | Unset = UNSET,
    rule_id: int | None | Unset = UNSET,
    incident_id: None | str | Unset = UNSET,
    acknowledged: bool | None | Unset = UNSET,
    is_test: bool | None | Unset = UNSET,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> Response[HTTPValidationError | PageLogEntryRead]:
    """ Query notification log

     Paged log query. Filters: type, severity, suppressed (true/false), rule_id, time range (from/to
    ISO8601), free-text search on title.

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        type_ (None | str | Unset):
        severity (None | Severity | Unset):
        suppressed (bool | None | Unset): true → only suppressed; false → only dispatched; omit →
            all
        delivery_status (None | str | Unset): Exact settled outcome: sent | partial | failed |
            suppressed.
        rule_id (int | None | Unset):
        incident_id (None | str | Unset):
        acknowledged (bool | None | Unset):
        is_test (bool | None | Unset): true → only test fires; false → only real.
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):
        search (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PageLogEntryRead]
     """


    kwargs = _get_kwargs(
        skip=skip,
limit=limit,
type_=type_,
severity=severity,
suppressed=suppressed,
delivery_status=delivery_status,
rule_id=rule_id,
incident_id=incident_id,
acknowledged=acknowledged,
is_test=is_test,
from_=from_,
to=to,
search=search,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    skip: int | Unset = 0,
    limit: int | Unset = 50,
    type_: None | str | Unset = UNSET,
    severity: None | Severity | Unset = UNSET,
    suppressed: bool | None | Unset = UNSET,
    delivery_status: None | str | Unset = UNSET,
    rule_id: int | None | Unset = UNSET,
    incident_id: None | str | Unset = UNSET,
    acknowledged: bool | None | Unset = UNSET,
    is_test: bool | None | Unset = UNSET,
    from_: datetime.datetime | None | Unset = UNSET,
    to: datetime.datetime | None | Unset = UNSET,
    search: None | str | Unset = UNSET,

) -> HTTPValidationError | PageLogEntryRead | None:
    """ Query notification log

     Paged log query. Filters: type, severity, suppressed (true/false), rule_id, time range (from/to
    ISO8601), free-text search on title.

    Args:
        skip (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        type_ (None | str | Unset):
        severity (None | Severity | Unset):
        suppressed (bool | None | Unset): true → only suppressed; false → only dispatched; omit →
            all
        delivery_status (None | str | Unset): Exact settled outcome: sent | partial | failed |
            suppressed.
        rule_id (int | None | Unset):
        incident_id (None | str | Unset):
        acknowledged (bool | None | Unset):
        is_test (bool | None | Unset): true → only test fires; false → only real.
        from_ (datetime.datetime | None | Unset):
        to (datetime.datetime | None | Unset):
        search (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PageLogEntryRead
     """


    return (await asyncio_detailed(
        client=client,
skip=skip,
limit=limit,
type_=type_,
severity=severity,
suppressed=suppressed,
delivery_status=delivery_status,
rule_id=rule_id,
incident_id=incident_id,
acknowledged=acknowledged,
is_test=is_test,
from_=from_,
to=to,
search=search,

    )).parsed
