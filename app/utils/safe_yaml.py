"""Depth- and alias-bounded YAML loading for config import (audit A-08).

``yaml.safe_load`` blocks arbitrary object construction but not resource
exhaustion: anchors/aliases can expand a tiny document exponentially (the
"billion laughs" attack), and deep nesting can exhaust the stack. Config import
has no need for either, so this loader **rejects aliases outright** and caps
nesting depth. Pair it with the global request-body cap (which bounds the raw
input size) and run it off the event loop for large inputs.
"""
from __future__ import annotations

from typing import Any

import yaml
from yaml.events import AliasEvent


class BoundedYAMLError(ValueError):
    """Raised when a config document violates a structural bound."""


def load_bounded(text: str, max_depth: int) -> Any:
    """Parse ``text`` as YAML with no aliases and a nesting-depth cap.

    Raises :class:`BoundedYAMLError` on an alias, on exceeding ``max_depth``,
    or on any ``yaml.YAMLError`` (so callers catch a single type).
    """

    class _Loader(yaml.SafeLoader):
        _depth: int = 0

    def compose_node(self: _Loader, parent, index):  # type: ignore[no-untyped-def]
        if self.check_event(AliasEvent):
            raise BoundedYAMLError("YAML aliases/anchors are not permitted in config")
        depth = getattr(self, "_depth", 0) + 1
        if depth > max_depth:
            raise BoundedYAMLError(f"YAML nesting exceeds max depth {max_depth}")
        self._depth = depth
        try:
            return yaml.SafeLoader.compose_node(self, parent, index)
        finally:
            self._depth = depth - 1

    _Loader.compose_node = compose_node  # type: ignore[assignment]
    try:
        return yaml.load(text, Loader=_Loader)
    except BoundedYAMLError:
        raise
    except yaml.YAMLError as e:
        raise BoundedYAMLError(f"YAML parse error: {e}") from e
