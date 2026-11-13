"""Admin UI — static single-page app served by alertd at ``/admin/``.

By design, the UI lives in
this container, talks only to the public ``/v1/*`` API with the
browser-session cookie (``app/auth.py``), and is plain static files
(Preact + htm, vendored, no bundler — see ``static/vendor/README.md``).

Mounting is controlled by ``ALERTD_ADMIN_UI_ENABLED``. The API is
unaffected either way.

Caching: every asset is served with ``Cache-Control: no-cache`` — the
browser revalidates with the ETag/Last-Modified that StaticFiles
emits, so a deploy is picked up on the next load without cache-busting
query strings. The files are small; correctness beats a few 304s.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"
MOUNT_PATH = "/admin"

# Headers on every /admin response. The CSP is strict on purpose: the
# SPA has no inline scripts or styles, loads nothing from third
# parties, and talks only to its own origin (fetch + WebSocket).
SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-cache",
}


class AdminStaticFiles(StaticFiles):
    """StaticFiles that stamps the security + cache headers."""

    def file_response(self, *args, **kwargs) -> Response:  # type: ignore[override]
        resp = super().file_response(*args, **kwargs)
        for k, v in SECURITY_HEADERS.items():
            resp.headers[k] = v
        return resp


def mount_admin_ui(app: FastAPI) -> bool:
    """Mount the SPA if enabled. Returns True when mounted."""
    from ..config import get_settings

    if not get_settings().admin_ui_enabled:
        return False
    if not os.path.isdir(STATIC_DIR):  # pragma: no cover — packaging error
        raise RuntimeError(f"admin UI static dir missing: {STATIC_DIR}")
    app.mount(MOUNT_PATH, AdminStaticFiles(directory=str(STATIC_DIR), html=True), name="admin_ui")
    return True


__all__ = ["MOUNT_PATH", "SECURITY_HEADERS", "STATIC_DIR", "mount_admin_ui"]
