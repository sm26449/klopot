# Klopot client SDKs

Both are generated from the committed API contract, `openapi/v1.json`, by
`scripts/generate_sdks.sh` — never edit generated files by hand. The SDK drift
check (`scripts/check.sh`, CI) fails when they no longer match the spec, so an
API change regenerates them in the same commit.

| SDK | Path | Generated | Hand-written |
|-----|------|-----------|--------------|
| Python `klopot-client` (package `klopot_client`) | `sdk/python/` | everything (openapi-python-client 0.29.1, httpx + attrs) | — |
| TypeScript / JavaScript `@klopot/client` | `sdk/typescript/` | `src/schema.d.ts` (openapi-typescript 7.4.4) | `src/index.js` + `src/index.d.ts` (fetch wrapper) |

Not published to PyPI / npm yet — install from the repository.

## Python

```bash
pip install ./sdk/python
```

```python
from klopot_client import AuthenticatedClient
from klopot_client.api.fire import post_fire_v1_fire_post
from klopot_client.models import FireRequest, FireRequestContext

client = AuthenticatedClient(base_url="https://alerts.example.com", token=KEY,
                             prefix="", auth_header_name="X-API-Key")
res = post_fire_v1_fire_post.sync(client=client, body=FireRequest(
    type_="disk_full", context=FireRequestContext.from_dict({"host": "nas"}),
    idempotency_key="nas-disk"))
print(res.episode, res.id)
```

- The request field `type` is `type_` in Python (it would shadow the builtin).
- `prefix=""` + `auth_header_name="X-API-Key"`: Klopot keys are not Bearer tokens.
- Every endpoint is under `klopot_client.api.<tag>.<operation>` with `sync`,
  `asyncio` and `*_detailed` variants.
- The YAML-body endpoints (`/v1/config/validate`, `/v1/config/import`,
  `/v1/config/import/preview`) are not generated (the generator does not
  support YAML bodies): call them with plain `httpx`.

## TypeScript / JavaScript

```bash
npm install ./sdk/typescript
```

```js
import { createClient } from "@klopot/client";

const klopot = createClient({ baseUrl: "https://alerts.example.com", apiKey: process.env.KLOPOT_KEY });
await klopot.fire("disk_full", { host: "nas" }, { idempotency_key: "nas-disk" });
await klopot.resolve("disk_full", "nas-disk");
// anything else: klopot.request("GET", "/v1/log", { query: { limit: 10 } })
```

Works in browsers, Node ≥ 18, Deno and Bun (uses the global `fetch`). Errors
throw `KlopotError` with `status` and the response `body`. Types for every
path and schema are exported from `schema.d.ts` (`paths`, `components`).

## Regenerating

```bash
scripts/generate_sdks.sh          # after any change to openapi/v1.json
scripts/generate_sdks.sh --check  # what check.sh / CI run
```

Tool versions are pinned (`pyproject.toml` `[dev]`, `package.json`).
openapi-python-client 0.30 generates for the `httpx2` fork; stay on 0.29.1.
