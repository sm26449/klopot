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
from typing import Any
from .base import BaseInput, ValueCallback


class FileTailInput(BaseInput):
    kind = "file_tail"

    def __init__(self, *, name: str, config: dict[str, Any], on_value: ValueCallback) -> None:
        super().__init__(name=name, config=config, on_value=on_value)
        self._task: asyncio.Task | None = None
        self._count = 0

    async def start(self) -> None:
        # Must return promptly; the work runs in a task the adapter owns.
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        path = Path(self.config["path"])
        # (a real adapter would read in a thread: no blocking I/O on the loop)
        f = open(path, "r", encoding=self.config.get("encoding", "utf-8"))
        if self.config.get("from_end", True):
            f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(0.1)
                continue
            self._count += 1
            # ValueCallback = (topic, payload, source_kind)
            await self.on_value(str(path), line.strip(), self.kind)

    def health(self) -> dict[str, Any]:
        return {"connected": self._task is not None and not self._task.done(),
                "last_msg_ts": None, "msg_count": self._count, "error": None}
```

### 2. Register the kind

`app/inputs/__init__.py` (the input registry lives in the package
`__init__`, unlike channels, which have `app/channels/registry.py`):

```python
from .alertmanager import AlertmanagerInput
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
    "alertmanager": AlertmanagerInput,
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

Add the member to `InputKind` in `app/enums.py` — the one definition
(`enum.StrEnum`), re-exported by `app/schemas/common.py` and
`app/db/models.py`; never define a second enum there. Then a forward-only
Alembic migration to extend the MySQL ENUM column:

```python
class InputKind(enum.StrEnum):
    mqtt = "mqtt"
    http_poll = "http_poll"
    webhook = "webhook"
    ...                      # schedule, sms_inbox, email_imap, alertmanager
    file_tail = "file_tail"  # NEW
```

That's it for the backend. The kind is now creatable via
`POST /v1/inputs` with `{kind: "file_tail", config: {path: "/var/log/app.log"}}`.

### 4. (UI) Add a form fragment

The admin UI renders the editor for each input kind from the field
metadata in `app/meta_kinds.py` (served at `/v1/meta/kinds`). Add a
`file_tail` entry describing its `path` / `encoding` / `from_end` fields, plus its
help text in `app/admin_ui/static/i18n/en.js` and `ro.js`.

### 5. (Tests) Add a test

`tests/inputs/test_file_tail.py` — write a temp file, start adapter,
assert values delivered.

---

## Adding a new channel adapter

The current contract is `async send(notif, config: dict, *, idempotency_key=None)
-> SendResult`, with an optional asynchronous `healthcheck(config)` and
`close()`. `ChannelManager` caches one adapter instance per kind and closes
persistent resources at service shutdown. MQTT is the reference for owned
connections; webhook is the reference for configurable HTTP destinations.
The durable outbox owns notification retries; a transport reconnect loop must
not become an independent notification retry loop. Forward the stable delivery
identity whenever the provider/payload supports it.

Example: add `kind: discord` (richer than the generic webhook).

### 1. Implement the adapter

`app/channels/discord.py`:

```python
from __future__ import annotations
import httpx
from typing import Any
from ..config import get_settings
from ..utils.safe_http import EgressBlocked, ResponseTooLarge, safe_request
from .base import BaseChannel, Notification, SendResult


class DiscordChannel(BaseChannel):
    kind = "discord"

    async def send(self, notif: Notification, config: dict[str, Any],
                   *, idempotency_key: str | None = None) -> SendResult:
        url = config.get("webhook_url")
        if not url:
            return SendResult(ok=False, error="Missing webhook_url")
        embed = {
            "title": notif.title,
            "description": notif.message,
            "color": SEVERITY_COLORS[notif.severity],
            "timestamp": notif.fired_at.isoformat(),
        }
        try:
            r = await safe_request("POST", url, timeout=5.0,
                                   block_private=get_settings().block_private_egress, json={
                "username": config.get("username", "alertd"),
                "avatar_url": config.get("avatar_url"),
                "embeds": [embed],
            })
            return SendResult(ok=r.status_code in (200, 204),
                              error=None if r.status_code in (200, 204) else f"HTTP {r.status_code}")
        except (httpx.HTTPError, EgressBlocked, ResponseTooLarge):
            return SendResult(ok=False, error="Discord request failed")

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        try:
            r = await safe_request("HEAD", config["webhook_url"], timeout=2.0,
                                   block_private=get_settings().block_private_egress)
            return {"reachable": r.status_code < 500, "status": r.status_code}
        except (KeyError, httpx.HTTPError, EgressBlocked, ResponseTooLarge):
            return {"reachable": False, "error": "Discord probe failed"}


SEVERITY_COLORS = {"info": 0x3498DB, "warning": 0xF1C40F, "critical": 0xE74C3C}
```

### 2. Register

`app/channels/registry.py` adds `"discord": DiscordChannel`.

### 2b. Declare its secret fields

`app/secrets_registry.py` → `SECRET_FIELDS["channel"]["discord"]`
(see the input section above for why).

### 3. Schema enum

Add `discord = "discord"` to `ChannelKind` in `app/enums.py` (the one
definition, re-exported by `app/schemas/common.py` and `app/db/models.py`),
plus a forward-only Alembic migration extending the MySQL enum. Update
metadata and the secret registry alongside them.

### 4. (UI) form fragment + test

Same as inputs. Extras for channels:

- **Test kit.** `tests/channels/_kit.py` gives a fake `safe_request`, a
  `Notification` factory and `assert_http_contract`, which checks that a 2xx
  is `ok=True`, that a 5xx, a timeout, a connection error and an egress block
  are `ok=False` with an error, and that no secret ever appears in an error
  (use `_secrets.scrub(text, *secrets)` on upstream bodies). A new HTTP
  channel's test is ~40 lines — see `tests/channels/test_gotify_pushover.py`.
- **Provider references.** Return the provider's message id as
  `SendResult(response={"provider_ref": "<kind>:<id>"})`; it is stored on the
  delivery. If the provider keeps the message alive (repeat until
  acknowledged), add a `cancel` action and a status poll to
  `app/core/provider_lifecycle.py` instead of inventing a new queue.
- **Retry hints.** A 429 / 503 with `Retry-After` →
  `SendResult(ok=False, retry_after=<seconds>)` (the delivery is deferred, no
  attempt spent, breaker untouched); a refusal that will never succeed (e.g. a
  422) → `SendResult(ok=False, permanent=True)` (failed now, no retry, breaker
  untouched). Forward `idempotency_key` as the provider's idempotency header
  when it has one.
- **Intrusive kinds** (can wake someone up or cost money) go in
  `INTRUSIVE_CHANNEL_KINDS` in `app/meta_kinds.py`.

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
2. Add the member to `VariableSource` in `app/enums.py` (re-exported by
   `app/schemas/common.py` and `app/db/models.py`; plus an Alembic migration
   for the ENUM).
3. Declare its config fields in `app/meta_kinds.py` (`_VARIABLES`) so the
   admin UI can render the form.

The variable's config (URL, token, query, refresh interval) lives in the
`variables.config` JSON column. The API and import accept any JSON object
there: validate the kind-specific shape yourself, in both the REST write
(`_reject_uncompilable_config` in `app/api/v1/variables.py`) and config
import, alongside its runtime resolution.

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
  should normally be environment-variable references in `channels.config`;
  register any accepted literal credential for masking and merge behaviour.
- ❌ Shared state between adapters (e.g., a global httpx client).
  Each adapter owns its resources.
- ❌ Synchronous I/O in an `async def`. Wrap blocking SDK calls in
  `asyncio.to_thread()`.
- ❌ `try: ... except Exception: pass`. Return a failed `SendResult` with a safe error so
  the dispatcher records `failed_channels[name] = "<reason>"`.
