"""Email channel — async SMTP via aiosmtplib.

Config shape::

    {
      "smtp_host": "smtp.example.com",
      "smtp_port": 587,
      "username": "alerts@example.com",
      "password_ref": "SMTP_PASSWORD",     // env var name
      "from": "alerts@example.com",
      "to": ["ops@example.com", "oncall@example.com"],
      "use_tls": true,                      // STARTTLS (587) vs SSL (465) vs plain (25)
      "ssl": false                          // implicit SSL (port 465)
    }

Sends a multipart message with text + minimal severity-styled HTML
so most clients render with a colored header even without external
CSS. Plaintext is the canonical body — HTML is decorative.
"""
from __future__ import annotations

import asyncio
import html
import logging
import socket
from email.message import EmailMessage
from typing import Any

import aiosmtplib

from ..config import get_settings
from ..utils.safe_http import EgressBlocked, screen_and_pick_ip
from ._secrets import resolve_secret
from .base import BaseChannel, Notification, SendResult

logger = logging.getLogger(__name__)


_SEVERITY_COLOR = {
    "info": "#3498DB",
    "warning": "#F1C40F",
    "critical": "#E74C3C",
}


async def _connect_pinned(ip: str, port: int, limit_sec: float) -> socket.socket:
    """A non-blocking TCP socket connected to ``ip`` (already screened)."""
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setblocking(False)
    try:
        async with asyncio.timeout(limit_sec):
            await asyncio.get_running_loop().sock_connect(sock, (ip, port))
    except BaseException:
        sock.close()
        raise
    return sock


class EmailChannel(BaseChannel):
    kind = "email"

    async def send(
        self, notif: Notification, config: dict[str, Any],
        *, idempotency_key: str | None = None,
    ) -> SendResult:
        host = config.get("smtp_host")
        port = int(config.get("smtp_port", 587))
        username = config.get("username")
        # Canonical sender is `from_addr` (the UI field); accept the legacy
        # `from` alias and fall back to the username, as the UI promises
        # (audit F33) — previously the adapter read only `from`, so a
        # form-filled channel failed "missing from".
        from_addr = config.get("from_addr") or config.get("from") or username
        to_addrs = config.get("to") or []
        password = resolve_secret(config, "password", "password_ref")
        use_tls = bool(config.get("use_tls", True))
        use_ssl = bool(config.get("ssl", False))

        # Normalize recipients into an address list; the UI documents a
        # comma-separated string, which must be split, not wrapped as one
        # recipient (audit F33).
        if isinstance(to_addrs, str):
            to_addrs = [a.strip() for a in to_addrs.split(",") if a.strip()]

        if not host or not from_addr or not to_addrs:
            return SendResult(ok=False, error="email config missing host / from / to")

        # Screen smtp_host like any other egress target so an admin can't point
        # the channel at cloud metadata / link-local (always) or, under strict
        # egress, an internal host (audit S-09) — and connect to the address
        # that was screened, not to a second lookup that a rebinding DNS could
        # answer differently (review K24).
        try:
            pinned_ip = await screen_and_pick_ip(
                f"smtp://{host}:{port}", block_private=get_settings().block_private_egress)
        except EgressBlocked as e:
            return SendResult(ok=False, error=e.reason)

        msg = EmailMessage()
        subject_prefix = {"info": "[INFO]", "warning": "[WARN]", "critical": "[CRIT]"}.get(
            notif.severity, ""
        )
        msg["Subject"] = f"{subject_prefix} {notif.title}".strip()
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)
        # Plaintext canonical body
        msg.set_content(f"{notif.title}\n\n{notif.message}\n\n— Klopot")
        # HTML alternative (decorative)
        color = _SEVERITY_COLOR.get(notif.severity, "#888")
        msg.add_alternative(_render_html(notif, color), subtype="html")

        try:
            sock = await _connect_pinned(pinned_ip, port, 15.0)
            await aiosmtplib.send(
                msg,
                sock=sock,                 # already connected to the screened address
                hostname=host,             # TLS: SNI and certificate check on the real name
                username=username,
                password=password,
                use_tls=use_ssl,           # implicit TLS (port 465)
                start_tls=use_tls and not use_ssl,  # STARTTLS (port 587)
                timeout=15,
            )
            return SendResult(ok=True, response={"to": to_addrs})
        except aiosmtplib.errors.SMTPException as e:
            return SendResult(ok=False, error=f"SMTP: {type(e).__name__}: {e}")
        except (TimeoutError, OSError) as e:
            return SendResult(ok=False, error=f"network: {type(e).__name__}: {e}")

    async def healthcheck(self, config: dict[str, Any]) -> dict[str, Any]:
        host = config.get("smtp_host")
        port = int(config.get("smtp_port", 587))
        if not host:
            return {"reachable": False, "error": "no smtp_host"}
        try:
            pinned_ip = await screen_and_pick_ip(
                f"smtp://{host}:{port}", block_private=get_settings().block_private_egress)
        except EgressBlocked as e:
            return {"reachable": False, "error": e.reason}
        # Quick TCP probe of the screened address — a real SMTP handshake would be heavier
        try:
            sock = await _connect_pinned(pinned_ip, port, 5.0)
            sock.close()
            return {"reachable": True, "host": host, "port": port}
        except Exception as e:
            return {"reachable": False, "error": str(e)[:200]}


def _render_html(notif: Notification, color: str) -> str:
    """Minimal severity-styled HTML body.

    Notification title/message/icon can originate in untrusted fire
    context or declared inputs, so every such field is HTML-escaped
    before interpolation — otherwise a sender could inject markup,
    links or remote content into mail sent under our trusted identity
    (audit A-12). The decorative markup and the ``color`` (chosen from
    a fixed severity map by the caller) stay fixed. Intended line
    breaks in the message are restored as ``<br>`` only after escaping,
    since HTML collapses the raw newlines the plaintext part keeps.
    """
    icon = html.escape(notif.icon or "")
    title = html.escape(notif.title or "")
    severity = html.escape(notif.severity or "")
    message = html.escape(notif.message or "").replace("\n", "<br>")
    return (
        '<!doctype html><html><body style="font-family:sans-serif;'
        'background:#f5f5f5;padding:24px;color:#222">'
        f'<div style="max-width:560px;margin:0 auto;background:#fff;'
        f'border-radius:8px;overflow:hidden;border:1px solid #ddd">'
        f'<div style="background:{color};color:#fff;padding:14px 18px;'
        f'font-weight:600;font-size:16px">{icon} {title}</div>'
        f'<div style="padding:18px;line-height:1.5">'
        f'<p style="margin:0 0 10px">{message}</p>'
        f'<p style="margin:0;color:#888;font-size:12px">'
        f'severity: <b>{severity}</b> — fired {notif.fired_at}</p>'
        f'</div></div></body></html>'
    )
