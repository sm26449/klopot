# klopot-client

Python client for the Klopot REST API (`/v1`), generated from `openapi/v1.json`
by `scripts/generate_sdks.sh`. This README is kept by hand in
`sdk/python-README.md` and copied over the generator's own (whose examples use
placeholder endpoints and a Bearer header Klopot does not accept).

## Authenticate

Klopot machine keys (`alertd_…`) go in the `X-API-Key` header — not
`Authorization: Bearer`:

```python
from klopot_client import AuthenticatedClient

client = AuthenticatedClient(
    base_url="https://alerts.example.com",
    token=KEY,
    prefix="",
    auth_header_name="X-API-Key",
    raise_on_unexpected_status=True,
)
```

## Fire an alert

```python
from klopot_client.api.fire import post_fire_v1_fire_post
from klopot_client.models import FireRequest, FireRequestContext, FireResponse

body = FireRequest(type_="disk_full", context=FireRequestContext.from_dict({"host": "nas"}))
with client:
    response = post_fire_v1_fire_post.sync_detailed(client=client, body=body)
    if not isinstance(response.parsed, FireResponse):
        raise RuntimeError(f"fire failed: HTTP {response.status_code} {response.parsed}")
    print(response.parsed.id, response.parsed.dispatched)
```

`sync_detailed` / `asyncio_detailed` return `klopot_client.types.Response`
(`status_code`, `content`, `headers`, `parsed`); `sync` / `asyncio` return only
`parsed`. Errors are parsed as `ErrorDetail`, whose `detail` is a message, a
list of validation errors or an object such as `{"code": "TYPE_NOT_ALLOWED"}`;
a `413` is an `ErrorEnvelope`.

For asynchronous use, build the same client and use `async with client:` and
`await post_fire_v1_fire_post.asyncio_detailed(client=client, body=body)`.

## Transport options

Pass `httpx` options with `httpx_args`, or set your own client (httpx 0.28 —
`proxy=`, not `proxies=`):

```python
import httpx

client.set_httpx_client(httpx.Client(
    base_url="https://alerts.example.com",
    proxy="http://localhost:8030",
    headers={"X-API-Key": KEY},
))
```

`verify_ssl=False` or a CA bundle path is accepted by `AuthenticatedClient`
for a private certificate authority.

## More

`sdk/README.md` (both SDKs), `docs/API.md` (the contract: `/v1/fire`, the
`unknown_type` canary, errors). Endpoints whose body is YAML
(`/v1/config/validate`, `/import`, `/import/preview`) are not generated — call
them with plain HTTP.
