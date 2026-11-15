"""A resolved secret, fit to go into a header or a request."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_warned: set[str] = set()


def usable_secret(value: str, source: str) -> str | None:
    """``value`` with surrounding whitespace trimmed, or None when a control
    character remains inside it (review K08).

    A trailing space, CR or newline (a ``secrets.env`` line, a quoted ``\\n``)
    makes a header value illegal: the HTTP library refuses the request and
    quotes the header, token included, in its error — which is then stored.
    ``source`` names where the value came from (an env var or a config field),
    never the value; it is logged once per source.
    """
    trimmed = value.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in trimmed):
        if source not in _warned:
            _warned.add(source)
            logger.warning("secret %s contains a control character; refusing to use it", source)
        return None
    if trimmed != value and source not in _warned:
        _warned.add(source)
        logger.warning("secret %s has leading or trailing whitespace; it is trimmed", source)
    return trimmed or None
