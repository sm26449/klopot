# Extensibility — adding inputs and channels

Inputs (data sources) and channels (output destinations) are
**plug-ins**. Adding one is a small, well-scoped change with a
predictable file checklist.

The goal: when you want to add `kind: discord_webhook` next year,
it's a 100-line PR, not a refactor.

> The `file_tail` input, the `discord` channel and the `influxdb_query`
> variable source below are **worked examples — none of them exists in the
> tree**. The real adapters to copy from are `app/inputs/http_poll.py` and
> `app/channels/webhook.py`. Any adapter that makes an outbound HTTP call
> must go through `app/utils/safe_http.py` (SSRF screening + IP pinning),
> as those two do.

---

## Adding a new input adapter

Example: add `kind: file_tail` that watches a log file and emits a
value per line.

### 1. Implement the adapter

`app/inputs/file_tail.py`:

```python
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Callable, Awaitable
from .base import BaseInput, ValueCallback
from pydantic import BaseModel


class FileTailConfig(BaseModel):
    path: str
    encoding: str = "utf-8"
    from_end: bool = True


class FileTailInput(BaseInput):
    kind = "file_tail"
    config_schema = FileTailConfig

    def __init__(self, config: FileTailConfig, on_value: ValueCallback):
        self._cfg = config
        self._on_value = on_value
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        path = Path(self._cfg.path)
        f = open(path, "r", encoding=self._cfg.encoding)
        if self._cfg.from_end:
            f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(0.1)
                continue
            await self._on_value(
                topic=str(path),
                value=line.strip(),
                ts=asyncio.get_event_loop().time(),
            )

    def health(self) -> dict:
        return {"connected": self._task is not None and not self._task.done()}
```

### 2. Register the kind

`app/inputs/__init__.py` (the input registry lives in the package
`__init__`, unlike channels, which have `app/channels/registry.py`):

```python
from .mqtt import MQTTSubscriber
from .http_poll import HTTPPollInput
from .webhook import WebhookInput
from .sms_inbox import SMSInboxInput
from .file_tail import FileTailInput  # NEW

REGISTRY: dict[str, type[BaseInput]] = {
    "mqtt": MQTTSubscriber,
    "http_poll": HTTPPollInput,
    "webhook": WebhookInput,
    "sms_inbox": SMSInboxInput,
    "file_tail": FileTailInput,  # NEW
}
```

### 2b. Declare its secret fields

`app/secrets_registry.py` → `SECRET_FIELDS["input"]["file_tail"]`
lists every `config` key that holds a credential (resolve it in the
adapter through `resolve_secret_local(config, "<key>", "<key>_ref")`).

> **Also declare the kind's fields in `app/meta_kinds.py`** (under
> `_INPUTS` / `_CHANNELS` / `_VARIABLES`). That dict is the single
> source of truth the admin UI builds its forms from
> (`GET /v1/meta/kinds`); secret-ness is read back from the registry
> above so the two never drift. A kind missing here still works via
> the API but has no generated form.

This is what masks the value in API reads and audit snapshots and
makes `PATCH` keep it when omitted. Unregistered kinds fall back to a
name heuristic (`password`, `token`, `secret`, `api_key`, …) — do not
rely on it.

### 3. Add a config schema in the API enum

`InputKind` is defined twice and both need the new member:
`app/schemas/common.py` (API) and `app/db/models.py` (the DB enum — which
also means an Alembic migration to extend the column's ENUM):

```python
class InputKind(str, Enum):
    mqtt = "mqtt"
    http_poll = "http_poll"
    webhook = "webhook"
    file_tail = "file_tail"  # NEW
```

That's it for the backend. The kind is now creatable via
`POST /v1/inputs` with `{kind: "file_tail", config: {path: "/var/log/app.log"}}`.

### 4. (UI) Add a form fragment

The admin UI renders the editor for each input kind from the field
metadata in `app/meta_kinds.py` (served at `/v1/meta`). Add a
`file_tail` entry describing the `FileTailConfig` fields, plus its
help text in `app/admin_ui/static/i18n/en.js` and `ro.js`.

### 5. (Tests) Add a test

`tests/inputs/test_file_tail.py` — write a temp file, start adapter,
assert values delivered.

---

## Adding a new channel adapter

Example: add `kind: discord` (richer than the generic webhook).

### 1. Implement the adapter

`app/channels/discord.py`:

```python
from __future__ import annotations
import httpx
from pydantic import BaseModel
from .base import BaseChannel, Notification


class DiscordConfig(BaseModel):
    webhook_url: str
    username: str = "alertd"
    avatar_url: str | None = None


class DiscordChannel(BaseChannel):
    kind = "discord"
    config_schema = DiscordConfig

    async def send(self, notif: Notification, config: DiscordConfig) -> bool:
        embed = {
            "title": notif.title,
            "description": notif.message,
            "color": SEVERITY_COLORS[notif.severity],
            "timestamp": notif.fired_at,
        }
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(config.webhook_url, json={
                "username": config.username,
                "avatar_url": config.avatar_url,
                "embeds": [embed],
            })
            return r.status_code in (200, 204)

    async def healthcheck(self, config: DiscordConfig) -> dict:
        # Discord webhook URLs return 200 on GET with HEAD
        async with httpx.AsyncClient(timeout=2.0) as c:
            try:
                r = await c.head(config.webhook_url)
                return {"reachable": True, "status": r.status_code}
            except Exception as e:
                return {"reachable": False, "error": str(e)}


SEVERITY_COLORS = {"info": 0x3498DB, "warning": 0xF1C40F, "critical": 0xE74C3C}
```

### 2. Register

`app/channels/registry.py` adds `"discord": DiscordChannel`.

### 2b. Declare its secret fields

`app/secrets_registry.py` → `SECRET_FIELDS["channel"]["discord"]`
(see the input section above for why).

### 3. Schema enum

`app/schemas/channel.py` adds `discord = "discord"`.

### 4. (UI) form fragment + test

Same as inputs.

---

## Adding a new variable source

Variable sources beyond the core 5 (mqtt, aggregate, computed,
constant, schedule) are rarer but supported.

Example: add `source: influxdb_query` to pull a recent average from
InfluxDB on each tick.

### Steps

There is no per-source plug-in package for variables today: all five
sources are implemented inside `app/core/variable_resolver.py`. Adding
one means:

1. Implement the resolution in `app/core/variable_resolver.py` (follow
   how `computed` or `schedule` is handled there).
2. Add the member to `VariableSource` in **both** `app/schemas/common.py`
   and `app/db/models.py` (plus an Alembic migration for the ENUM).
3. Declare its config fields in `app/meta_kinds.py` (`_VARIABLES`) so the
   admin UI can render the form.

The variable's config (URL, token, query, refresh interval) lives in
the `variables.config` JSON column — kind-specific shape validated
by Pydantic at write time.

---

## Plugin loading model

We are not using `importlib.metadata` entry points or pkg_resources
plugin discovery, because:

1. All plugins are first-party (we own all the kinds).
2. Explicit registry maps are simpler to read and less magic.
3. Auditing what kinds exist = read one file.

If we ever need third-party plugins (e.g., users installing extras
into a fleet deployment), we'll switch to entry-point loading. The
only change required is adding a discovery loop to
`app/channels/registry.py` / `app/inputs/__init__.py` that merges third-party providers into `REGISTRY`.

---

## What NOT to add as a kind

Some integrations look like channels but are actually thin wrappers
around `webhook`:

- Slack, Discord (without rich embeds), Mattermost, MS Teams — all
  webhook URLs accepting JSON. Use the `webhook` channel and a
  custom `body_template`.
- Home Assistant — has a webhook trigger; use `webhook`.

We add a dedicated `kind` only when the integration needs:
- Custom auth flow (OAuth, signed requests)
- Rich payload with channel-specific features (Discord embeds,
  PagerDuty incidents)
- Bidirectional state (e.g., PagerDuty acknowledgements)

For everything else: configure a `webhook` channel and write the
template once.

---

## Anti-patterns

- ❌ Adding hardcoded behavior in `dispatcher.py` for "this kind is
  special". The dispatcher must be channel-agnostic.
- ❌ Storing channel credentials in the kind's Python code. They
  belong in `channels.config` JSON.
- ❌ Shared state between adapters (e.g., a global httpx client).
  Each adapter owns its resources.
- ❌ Synchronous I/O in an `async def`. Wrap blocking SDK calls in
  `asyncio.to_thread()`.
- ❌ `try: ... except Exception: pass`. Always log + return False so
  the dispatcher records `failed_channels[name] = "<reason>"`.
