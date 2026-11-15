"""One source-aware staleness policy, shared by the runtime mapping and
the ``/v1/variables`` API (audit F31).

Previously the two disagreed: a topic variable created without an explicit
``stale_after_sec`` was stored with ``None`` at runtime (never stale, so the
engine trusted a dead source forever) while the API reported it stale after
300 seconds; schedule variables were the reverse (latched/never-stale at
runtime but reported stale at 300). Resolving the effective policy in one
place keeps the engine and the API in agreement.

Policy:

* ``constant`` and ``schedule`` sources latch — they never go stale on a
  timer (a constant is fixed; a schedule slot holds until its next fire).
* every other source (``mqtt`` / ``aggregate`` / ``computed``) uses its
  explicit positive ``stale_after_sec`` if set, otherwise the 300 s default.
"""
from __future__ import annotations

from typing import Any

DEFAULT_STALE_SEC = 300

# Sources whose values latch and do not expire on a timer.
NEVER_STALE_SOURCES = frozenset({"constant", "schedule"})


def effective_stale_after_sec(source: Any, cfg_stale: Any) -> int | None:
    """Resolve the effective staleness window for a variable.

    Returns ``None`` for a never-stale source, otherwise the configured
    positive window or :data:`DEFAULT_STALE_SEC`.
    """
    src = str(getattr(source, "value", source) or "").lower()
    if src in NEVER_STALE_SOURCES:
        return None
    if isinstance(cfg_stale, bool):  # guard: bool is an int subclass
        return DEFAULT_STALE_SEC
    if isinstance(cfg_stale, int | float) and cfg_stale > 0:
        return int(cfg_stale)
    return DEFAULT_STALE_SEC
