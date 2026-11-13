"""Push channel — Web Push (VAPID) notifications.

Web Push delivers to browser service workers (and PWAs) via a
push service (FCM / Mozilla / Apple). Each browser session
generates a *subscription* on first opt-in; we store these per
user in the ``user_prefs`` table.

Config shape (one channel per VAPID key pair)::

    {
      "vapid_public_ref": "VAPID_PUBLIC_KEY",
      "vapid_private_ref": "VAPID_PRIVATE_KEY",
      "vapid_subject": "mailto:ops@pv.local",
      "ttl_sec": 3600
    }

Subscriptions live in ``user_prefs.settings.push_subscriptions``::

    [{"endpoint": "https://fcm...", "keys": {"p256dh":"...", "auth":"..."}}, ...]

For S6 we ship a working channel + a stub registration endpoint
(``POST /v1/push/subscribe``) that the future React UI calls. The
channel iterates ALL stored subscriptions across users (no per-rule
filtering yet — that's S10's user_prefs work).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select

from ..db.models import UserPref
from ._secrets import resolve_secret
from .base import BaseChannel, Notification, SendResult

logger = logging.getLogger(__name__)


class PushChannel(BaseChannel):
    kind = "push"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        try:
            from pywebpush import WebPushException, webpush
        except ImportError:
            return SendResult(ok=False, error="pywebpush not installed")

        public_key = resolve_secret(config, "vapid_public", "vapid_public_ref")
        private_key = resolve_secret(config, "vapid_private", "vapid_private_ref")
        # Accept the UI's `subject` field as an alias for `vapid_subject`
        # (audit F34) — the metadata emitted `subject`, so a filled form
        # otherwise failed "missing ... subject".
        subject = config.get("vapid_subject") or config.get("subject")
        if not (public_key and private_key and subject):
            return SendResult(
                ok=False,
                error="push config missing vapid keys or subject",
            )

        # Load subscriptions from user_prefs
        subs = await _load_subscriptions()
        if not subs:
            return SendResult(
                ok=True,
                response={"subscriptions": 0, "delivered": 0, "errors": []},
            )

        payload = json.dumps({
            "title": notif.title,
            "message": notif.message,
            "severity": notif.severity,
            "icon": notif.icon or "",
            "type": notif.type,
            "id": notif.id,
            "tag": notif.type,  # browsers coalesce same-tag pushes
        })

        ttl = int(config.get("ttl_sec", 3600))
        delivered = 0
        errors: list[str] = []
        stale: list[dict[str, Any]] = []

        for sub in subs:
            try:
                # webpush is sync; run it in a thread to avoid blocking
                import asyncio

                await asyncio.to_thread(
                    webpush,
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=private_key,
                    vapid_claims={"sub": subject},
                    ttl=ttl,
                )
                delivered += 1
            except WebPushException as e:
                # 410 = gone; subscription expired — flag for cleanup
                if "410" in str(e):
                    stale.append(sub)
                errors.append(str(e)[:120])
            except Exception as e:
                errors.append(f"{type(e).__name__}: {e}"[:120])

        # Best-effort cleanup of stale subscriptions
        if stale:
            await _remove_stale(stale)

        # Channel succeeds if at least ONE subscription got the push
        # (or there were none — empty fan-out is not a failure)
        ok = (not subs) or (delivered > 0)
        return SendResult(
            ok=ok,
            error="; ".join(errors[:3]) if (not ok and errors) else None,
            response={"subscriptions": len(subs), "delivered": delivered, "errors": errors},
        )

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        try:
            import pywebpush  # noqa: F401

            installed = True
        except ImportError:
            installed = False
        return {
            "reachable": installed,
            "lib_installed": installed,
        }


async def _load_subscriptions() -> list[dict[str, Any]]:
    """Read all push_subscriptions across user_prefs rows."""
    from ..db import get_session

    out: list[dict[str, Any]] = []
    async for s in get_session():
        rows = (await s.execute(select(UserPref))).scalars().all()
        for r in rows:
            settings = r.settings or {}
            subs = settings.get("push_subscriptions") or []
            if isinstance(subs, list):
                out.extend(s for s in subs if isinstance(s, dict))
        break
    return out


async def _remove_stale(stale: list[dict[str, Any]]) -> None:
    """Drop expired subscription endpoints from user_prefs."""
    from ..db import get_session

    stale_endpoints = {s.get("endpoint") for s in stale if s.get("endpoint")}
    if not stale_endpoints:
        return
    async for s in get_session():
        rows = (await s.execute(select(UserPref))).scalars().all()
        changed = False
        for r in rows:
            settings = dict(r.settings or {})
            subs = settings.get("push_subscriptions") or []
            if not isinstance(subs, list):
                continue
            kept = [
                sub for sub in subs
                if isinstance(sub, dict) and sub.get("endpoint") not in stale_endpoints
            ]
            if len(kept) != len(subs):
                settings["push_subscriptions"] = kept
                r.settings = settings
                changed = True
        if changed:
            await s.commit()
        break
