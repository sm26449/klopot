"""HTTP poll input — periodic GET against an external URL.

Use case: data sources without MQTT (REST APIs, status endpoints,
etc.). The adapter spawns a background task that polls every
``interval_sec`` and feeds the response into the resolver as if it
arrived on topic ``http_poll:<input_name>``.

Config shape::

    {
      "url": "https://api.example.com/status",
      "method": "GET",                          // GET/POST
      "interval_sec": 60,
      "timeout_sec": 10,
      "headers": {"X-Custom": "value"},
      "auth_kind": "bearer" | "basic" | "header" | null,
      "auth_value_ref": "API_TOKEN_ENV_VAR",    // env var name
      "params": {"key": "value"}                // query string
    }

Variables map to the virtual topic ``http_poll:<input_name>`` with
``json_path`` to drill into the response. Plaintext responses come
through with ``json_path: null``.

Resilience: timeouts and 4xx/5xx are logged and skipped. The poll
loop continues. ``last_error`` is exposed via the health probe.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from ..config import get_settings
from ..utils.safe_http import EgressBlocked, ResponseTooLarge, safe_request
from ._secrets_helper import resolve_secret_local
from .base import BaseInput, ValueCallback

logger = logging.getLogger(__name__)


class HTTPPollInput(BaseInput):
    """One persistent poll loop per declared HTTP input."""

    kind = "http_poll"

    def __init__(self, *, name: str, config: dict[str, Any], on_value: ValueCallback) -> None:
        super().__init__(name=name, config=config, on_value=on_value)
        self._task: asyncio.Task[None] | None = None
        self._stop_evt = asyncio.Event()

        # Health
        self._connected: bool = False
        self._last_msg_ts: float | None = None
        self._msg_count: int = 0
        self._last_error: str | None = None
        self._bad_json = False  # warned about an unparsable JSON answer (once per run)

    @property
    def topic(self) -> str:
        return f"http_poll:{self.name}"

    # ── BaseInput surface ─────────────────────────────────────────

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run(), name=f"http-poll-{self.name}")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def health(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "last_msg_ts": self._last_msg_ts,
            "msg_count": self._msg_count,
            "error": self._last_error,
            "topic": self.topic,
        }

    async def update_topics(self, topics: dict[str, Any]) -> None:
        # No filter — every successful poll feeds the single virtual topic
        return None

    # ── Internals ─────────────────────────────────────────────────

    async def _run(self) -> None:
        url = self.config.get("url")
        if not url:
            logger.error("HTTPPoll %s: missing url; not polling", self.name)
            self._last_error = "missing url"
            return

        # SSRF egress policy (A-04) is enforced per poll inside ``_poll_once``
        # via connect-time IP pinning — not once up front — so a target that
        # rebinds to a metadata/link-local (or, when configured, private)
        # address is caught on every connection, and one that becomes valid
        # again recovers without a restart.
        interval = max(1, int(self.config.get("interval_sec", 60)))
        timeout = float(self.config.get("timeout_sec", 10.0))
        method = (self.config.get("method") or "GET").upper()
        params = self.config.get("params") or None
        headers = dict(self.config.get("headers") or {})

        # Auth
        auth_kind = self.config.get("auth_kind")
        if auth_kind:
            auth_value = resolve_secret_local(self.config, "auth_value", "auth_value_ref")
            if auth_value:
                if auth_kind == "bearer":
                    headers["Authorization"] = f"Bearer {auth_value}"
                elif auth_kind == "basic":
                    headers["Authorization"] = f"Basic {auth_value}"
                elif auth_kind == "header" and ":" in auth_value:
                    h_name, _, h_val = auth_value.partition(":")
                    headers[h_name.strip()] = h_val.strip()

        logger.info(
            "HTTPPoll %s: GET %s every %ds",
            self.name, url, interval,
        )

        while not self._stop_evt.is_set():
            try:
                await self._poll_once(url, method, headers, params, timeout)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("HTTPPoll %s tick failed", self.name)
            try:
                await asyncio.wait_for(self._stop_evt.wait(), timeout=interval)
                return  # stop event fired during sleep
            except TimeoutError:
                pass

    async def _poll_once(
        self,
        url: str,
        method: str,
        headers: dict[str, str],
        params: dict | None,
        timeout: float,  # noqa: ASYNC109 — plain httpx timeout value, not a cancel scope
    ) -> None:
        try:
            r = await safe_request(
                method, url, headers=headers, params=params, timeout=timeout,
                block_private=get_settings().block_private_egress,
            )
        except EgressBlocked as e:
            self._connected = False
            self._last_error = e.reason
            logger.error(
                "HTTPPoll %s refused by egress policy: %s", self.name, e.reason
            )
            return
        except ResponseTooLarge as e:
            self._connected = False
            self._last_error = "ResponseTooLarge"
            logger.warning("HTTPPoll %s: %s", self.name, e.reason)
            return
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            self._connected = False
            # Store a stable category only — the exception string can embed
            # the target URL (and any credentials in it). Full detail goes to
            # the logs, which the redacting filter sanitizes (audit A-07).
            self._last_error = type(e).__name__
            logger.warning(
                "HTTPPoll %s request failed: %s: %s", self.name, type(e).__name__, e
            )
            return

        if r.status_code >= 400:
            self._connected = False
            # The status code is a safe category; the upstream response body is
            # NOT — it can echo credentials — so it never enters the stored
            # error or any health response (audit A-07). Body → debug logs only.
            self._last_error = f"HTTP {r.status_code}"
            logger.warning("HTTPPoll %s upstream returned HTTP %s", self.name, r.status_code)
            logger.debug("HTTPPoll %s upstream body: %s", self.name, r.text[:200])
            return

        self._connected = True
        self._last_error = None
        self._msg_count += 1
        self._last_msg_ts = time.time()

        # Parse: JSON if the response is JSON, else text
        payload: Any = r.text
        ct = r.headers.get("content-type", "").lower()
        if "application/json" in ct or r.text.lstrip().startswith(("{", "[")):
            try:
                payload = r.json()
                self._bad_json = False
            except ValueError as e:
                # Used as text, as before — but say so, once per run of bad
                # answers: a rule reading a JSON field just sees no value.
                if not self._bad_json:
                    logger.warning("HTTPPoll %s: the answer looks like JSON but does not parse (%s); "
                                   "using it as text", self.name, type(e).__name__)
                self._bad_json = True

        try:
            await self.on_value(self.topic, payload, "http_poll")
        except Exception as e:
            # Category only — the handler's error text can carry payload data
            # or a resolved URL; keep raw detail to the logs (audit A-07).
            self._last_error = f"resolver: {type(e).__name__}"
            logger.warning(
                "HTTPPoll %s value handling failed: %s: %s", self.name, type(e).__name__, e
            )
