"""The size and shape a caller's ``context`` may have.

``context`` (``POST /v1/fire``) is stored with the notification, hashed for
de-duplication and walked when the template renders. Only the 1 MiB request
cap bounded it, and an unknown ``type`` stored it even though nothing was
sent (public-exposure review, Codex #3). The budget: its compact JSON in
UTF-8 within ``max_bytes`` (``ALERTD_FIRE_CONTEXT_MAX_BYTES``) and nesting
no deeper than ``MAX_DEPTH``. Pure, so a schema validator and an ingest path
can share it.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

MAX_DEPTH = 16


def context_bytes(context: Any) -> int:
    """The size of ``context`` as compact JSON, in UTF-8 bytes. A lone
    surrogate (accepted, and stored as U+FFFD — utils/text.py) counts as the
    3 bytes it becomes instead of failing the measurement."""
    text = json.dumps(context, separators=(",", ":"), ensure_ascii=False, default=str)
    return len(text.encode("utf-8", errors="surrogatepass"))


def context_depth(context: Any) -> int:
    """How deeply ``context`` nests (a scalar is 0, ``{"a": 1}`` is 1).
    Iterative, so a pathological value cannot exhaust the stack."""
    deepest = 0
    stack: list[tuple[Any, int]] = [(context, 0)]
    while stack:
        value, depth = stack.pop()
        children: Iterable[Any]
        if isinstance(value, dict):
            children = value.values()
        elif isinstance(value, list | tuple):
            children = value
        else:
            deepest = max(deepest, depth)
            continue
        deepest = max(deepest, depth + 1)
        stack.extend((child, depth + 1) for child in children)
    return deepest


def check_context(context: Any, *, max_bytes: int) -> None:
    """Raise ``ValueError`` (naming the limit and its setting) when
    ``context`` nests deeper than ``MAX_DEPTH`` or exceeds ``max_bytes``."""
    depth = context_depth(context)
    if depth > MAX_DEPTH:
        raise ValueError(f"context nests {depth} levels deep; the limit is {MAX_DEPTH}")
    size = context_bytes(context)
    if size > max_bytes:
        raise ValueError(
            f"context is {size} bytes; the limit is {max_bytes} (ALERTD_FIRE_CONTEXT_MAX_BYTES) — "
            "send what the template needs, not whole documents"
        )
