"""Local copy of secret resolver for inputs.

Mirrors ``app.channels._secrets`` but lives in ``app.inputs`` so
inputs don't depend on the channels package.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from ..config import get_settings
from ..utils.secret_value import usable_secret

logger = logging.getLogger(__name__)


def resolve_secret_local(
    config: dict[str, Any],
    plain_key: str,
    ref_key: str,
) -> str | None:
    """Return the secret value, or None if missing.

    Order: ``config[ref_key]`` (env var name) → ``config[plain_key]``
    literal. Production uses ``_ref`` so secrets stay out of the DB.
    """
    ref_name = config.get(ref_key)
    if ref_name:
        # Default-deny allowlist, same as the channel resolver (audit S-04): an
        # input ref must not be pointed at ALERTD_DATABASE_URL (or any other
        # process secret) and exfiltrated to an arbitrary poll/webhook target.
        if not get_settings().secret_ref_allowed(str(ref_name)):
            logger.warning(
                "input secret ref %r is not allowlisted (name it KLOPOT_SECRET_..., or set ALERTD_SECRET_REF_ALLOW "
                "to permit it); refusing to resolve",
                ref_name,
            )
        else:
            val = os.environ.get(str(ref_name))
            if val:
                return usable_secret(val, f"env {ref_name}")
    plain = config.get(plain_key)
    if plain:
        return usable_secret(str(plain), f"field {plain_key}")
    return None
