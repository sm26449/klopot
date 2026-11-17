"""Kurier watches Klopot (ADR-0003; the contract is Kurier ADR-0001).

Every ``PING_EVERY_SEC`` this task pings each enabled ``kurier`` SMS channel
whose ``watchdog`` is on: ``POST {kurier_url}/api/watchdogs/klopot-<channel>/ping``
with Klopot's own health. Kurier sends an SMS when the pings stop (Klopot dead)
or say ``fail`` (Klopot alive but stuck — the engine, the delivery worker, the
outbox). The answer carries Kurier's modem state, so one request checks both
directions: Klopot raises ``kurier_unreachable`` after ``UNREACHABLE_AFTER``
failed pings and ``kurier_modem_down`` when the modem is off the network —
episodes of their own (``source_kind`` ``kurier``), each with its recovery
template, routed like the other self-monitoring alerts (never only to SMS:
that is the path that is down).

A task of its own, never the rule engine's loop: the engine must not wait on
the network (IP-01), and its health — not its own pings — is what this sends.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, true

from ..channels.sms import kurier_headers, recipients
from ..channels.sms_config import kurier_base, watchdog_timeout
from ..config import get_settings
from ..db.models import Channel, ChannelKind
from ..db.session import get_session
from ..utils.redact import transport_error_text
from ..utils.safe_http import EgressBlocked, safe_request
from . import fire_service
from .health import ComponentHealth, collect_components, essential_down

logger = logging.getLogger(__name__)

PING_EVERY_SEC = 60
PING_TIMEOUT_SEC = 10
UNREACHABLE_AFTER = 3          # failed pings in a row before Klopot says so
DETAIL_MAX = 160               # Kurier keeps at most this much of `detail`
SOURCE_KIND = "kurier"


def watchdog_name(channel_name: str) -> str:
    """``klopot-<channel>`` in Kurier's name alphabet ``[a-z0-9._-]``, ≤ 64."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", channel_name.lower()).strip("-._") or "sms"
    return f"klopot-{slug}"[:64]


def verdict(components: dict[str, ComponentHealth]) -> tuple[str, str]:
    """``("ok", "")``, or ``("fail", why)``: an essential component is down
    (database, rule engine — also when stuck —, delivery worker) or the
    outbox is not draining. The same rules as ``/v1/health/ready``."""
    failing = list(essential_down(components))
    if components.get("outbox") is not None and components["outbox"].status == "degraded":
        failing.append("outbox")
    if not failing:
        return "ok", ""
    detail = "; ".join(f"{name}: {components[name].detail or components[name].status}" for name in failing)
    return "fail", detail[:DETAIL_MAX]


def ping_body(config: dict[str, Any], status: str, detail: str) -> dict[str, Any]:
    body: dict[str, Any] = {"timeout_sec": watchdog_timeout(config), "status": status}
    if detail:
        body["detail"] = detail
    to = recipients({"phone": config.get("watchdog_to") or ""})
    if to:
        body["to"] = to
    return body


@dataclass
class PingResult:
    ok: bool
    error: str = ""
    modem: dict[str, Any] | None = None


async def ping(config: dict[str, Any], name: str, status: str, detail: str) -> PingResult:
    url = f"{kurier_base(config)}/api/watchdogs/{name}/ping"
    try:
        headers = kurier_headers(config)
    except Exception as e:     # no key resolved: say so, never the key
        return PingResult(False, str(e))
    try:
        r = await safe_request("POST", url, json=ping_body(config, status, detail), headers=headers,
                               timeout=PING_TIMEOUT_SEC, block_private=get_settings().block_private_egress)
    except EgressBlocked as e:
        return PingResult(False, e.reason)
    except Exception as e:     # transport: refused, timeout, DNS
        return PingResult(False, transport_error_text(e)[:200])
    if r.status_code != 200:
        if r.status_code == 404:
            return PingResult(False, "HTTP 404 (Kurier without watchdogs — needs Kurier 1.15+)")
        # 401 wrong key, 422 a bad setting (timeout, recipients), 409 too many
        # watchdogs, 503 Kurier without a key: its `detail` says which.
        try:
            why = _detail_text((r.json() or {}).get("detail"))
        except (ValueError, AttributeError):
            why = ""
        return PingResult(False, f"HTTP {r.status_code}" + (f": {why[:120]}" if why else ""))
    try:
        body = r.json()
    except ValueError:
        body = {}
    modem = body.get("modem") if isinstance(body, dict) else None
    return PingResult(True, modem=modem if isinstance(modem, dict) else None)


def _detail_text(detail: Any) -> str:
    """Kurier's ``detail``: a string, or FastAPI's validation list
    (``[{"loc": …, "msg": …}, …]``) — joined by its messages."""
    if isinstance(detail, list):
        return "; ".join(str(d.get("msg") or d) if isinstance(d, dict) else str(d) for d in detail)
    return str(detail or "")


def modem_down(modem: dict[str, Any] | None) -> bool:
    """Only an explicit ``registered: false`` — unknown is not down."""
    return bool(modem) and modem.get("registered") is False   # type: ignore[union-attr]


class KurierWatchdog:
    """The ping loop. In-memory failure counts per channel; the episodes are
    in the database, so a restart neither loses nor repeats an alert."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._failures: dict[int, int] = {}

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="kurier-watchdog")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def is_alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("kurier watchdog tick failed")
            await asyncio.sleep(PING_EVERY_SEC)

    async def tick(self) -> None:
        async for session in get_session():
            channels = await _watched(session)
            if channels:
                status, detail = verdict(await collect_components())
                for channel in channels:
                    result = await ping(channel.config, watchdog_name(channel.name), status, detail)
                    await self._record(session, channel, result)
                await session.commit()
            break

    async def _record(self, session: Any, channel: Channel, result: PingResult) -> None:
        base = {"channel": channel.name, "kurier_url": kurier_base(channel.config)}
        unreachable = f"{SOURCE_KIND}:{channel.id}:unreachable"
        modem = f"{SOURCE_KIND}:{channel.id}:modem"
        if not result.ok:
            count = self._failures.get(channel.id, 0) + 1
            self._failures[channel.id] = count
            if count >= UNREACHABLE_AFTER:
                await fire_service.fire_episode(
                    session, source_kind=SOURCE_KIND, source_key=unreachable, name=f"Kurier unreachable ({channel.name})",
                    type="kurier_unreachable", context={**base, "error": result.error, "failed_pings": count},
                    source="klopot", resolved_type="kurier_reachable")
            return
        self._failures[channel.id] = 0
        await fire_service.resolve_episode(session, source_key=unreachable, context=base)
        state = {**base, **{k: (result.modem or {}).get(k) for k in ("signal_strength", "sim_state", "operator")}}
        if modem_down(result.modem):
            await fire_service.fire_episode(
                session, source_kind=SOURCE_KIND, source_key=modem, name=f"Kurier modem offline ({channel.name})",
                type="kurier_modem_down", context=state, source="klopot", resolved_type="kurier_modem_up")
        else:
            await fire_service.resolve_episode(session, source_key=modem, context=state)


async def _watched(session: Any) -> list[Channel]:
    rows = (await session.execute(
        select(Channel).where(Channel.kind == ChannelKind.sms, Channel.enabled == true())
    )).scalars().all()
    return [c for c in rows if (c.config or {}).get("provider") == "kurier" and (c.config or {}).get("watchdog")
            and kurier_base(c.config)]


_service: KurierWatchdog | None = None


def get_kurier_watchdog() -> KurierWatchdog:
    global _service
    if _service is None:
        _service = KurierWatchdog()
    return _service
