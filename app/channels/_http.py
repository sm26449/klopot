"""Outbound HTTP shared by the channel adapters.

Every HTTP adapter made the same ``safe_request`` call and mapped the same
failures the same way; it lives here once. ``request`` returns the response or
raises :class:`Failed` carrying the ``SendResult`` to return; ``probe`` is the
reachability check of a channel test. What stays in an adapter is what is its
own: the payload, which statuses count as delivered, the provider's ids.

Errors never carry a secret: httpx quotes the request URL, so transport errors
go through ``transport_error_text`` and the adapter's ``clean`` (which removes
its token or URL) before they are stored on a delivery or shown.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from ..config import get_settings
from ..utils.redact import transport_error_text
from ..utils.safe_http import EgressBlocked, ResponseTooLarge, safe_request
from .base import HEALTHCHECK_TIMEOUT_SEC, SendResult

_ERROR_MAX = 200


def _as_is(text: str) -> str:
    return text


class Failed(Exception):
    """The request did not get an HTTP answer; ``result`` says why."""

    def __init__(self, result: SendResult) -> None:
        super().__init__(result.error)
        self.result = result


async def request(
    name: str, method: str, url: str, *, timeout: float,  # noqa: ASYNC109 — httpx timeout value
    clean: Callable[[str], str] = _as_is, **kwargs: Any,
) -> httpx.Response:
    """``safe_request`` with the adapters' common failure mapping. ``name``
    prefixes the error ("ntfy timeout"); ``clean`` scrubs the adapter's
    secrets out of a transport error."""
    try:
        return await safe_request(method, url, timeout=timeout,
                                  block_private=get_settings().block_private_egress, **kwargs)
    except (EgressBlocked, ResponseTooLarge) as e:
        raise Failed(SendResult(ok=False, error=e.reason)) from None
    except httpx.TimeoutException:
        raise Failed(SendResult(ok=False, error=f"{name} timeout")) from None
    except httpx.HTTPError as e:
        text = clean(f"{name} HTTP error: {transport_error_text(e)}")[:_ERROR_MAX]
        raise Failed(SendResult(ok=False, error=text)) from None


def reachable(r: httpx.Response) -> dict[str, Any]:
    """Default probe verdict: any answer below 500 means the service is there."""
    return {"reachable": r.status_code < 500, "status": r.status_code}


async def probe(
    method: str, url: str, read: Callable[[httpx.Response], dict[str, Any]] = reachable, *,
    clean: Callable[[str], str] = _as_is, **kwargs: Any,
) -> dict[str, Any]:
    """A channel test's reachability check; never raises."""
    try:
        r = await safe_request(method, url, timeout=HEALTHCHECK_TIMEOUT_SEC,
                               block_private=get_settings().block_private_egress, **kwargs)
        return read(r)
    except EgressBlocked as e:
        return {"reachable": False, "error": e.reason}
    except Exception as e:
        return {"reachable": False, "error": clean(transport_error_text(e))[:_ERROR_MAX]}
