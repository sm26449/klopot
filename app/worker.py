"""The gunicorn worker class the image runs (Dockerfile CMD).

uvicorn's worker with two of its defaults turned off:
- ``server_header``: no ``server: uvicorn`` on every response — it names the
  stack to anyone who asks (review F13);
- ``proxy_headers``: X-Forwarded-For / -Proto are honoured by Klopot itself,
  from ``ALERTD_TRUSTED_PROXY_CIDRS`` (``app.forwarded``, ``utils.client_ip``),
  not by a second list in gunicorn (``forwarded_allow_ips``).
"""
from __future__ import annotations

from typing import Any, ClassVar

from uvicorn_worker import UvicornWorker


class KlopotWorker(UvicornWorker):  # type: ignore[misc]  # untyped base (uvicorn-worker has no stubs)
    CONFIG_KWARGS: ClassVar[dict[str, Any]] = {
        **UvicornWorker.CONFIG_KWARGS, "server_header": False, "proxy_headers": False,
    }
