"""Text that a database and a JSON encoder will accept."""
from __future__ import annotations

import re
from typing import Any

_SURROGATE = re.compile("[\ud800-\udfff]")


def _clean_str(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        # A lone UTF-16 surrogate ("\\ud800" in JSON is accepted by
        # json.loads): no UTF-8 form exists, so the driver refuses the row.
        return _SURROGATE.sub("\ufffd", value)
    return value


def clean_text(value: Any) -> Any:
    """``value`` with every lone surrogate in its strings (dict keys included)
    replaced by U+FFFD. Dicts and lists are always copied; tuples become lists."""
    if isinstance(value, str):
        return _clean_str(value)
    if isinstance(value, dict):
        return {clean_text(k): clean_text(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [clean_text(v) for v in value]
    return value
