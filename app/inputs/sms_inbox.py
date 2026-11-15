"""SMS inbox input — Teltonika SMS forwarder receiver.

Specialization of the webhook input that normalizes the Teltonika
RUT241 SMS shape into a consistent schema before handing off to the
resolver.

Teltonika forwards a JSON body like::

    {
      "from": "+15555550100",
      "body": "STATUS",
      "received_at": "2026-05-10T08:00:00Z",
      "modem": "lte0"
    }

Variables can map by JSONPath: ``json_path: "body"``,
``json_path: "from"``, etc.

Point the gateway's incoming-SMS forwarder at
``/v1/inputs/{id}/webhook`` so every received SMS is POSTed here.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from .webhook import WebhookInput

logger = logging.getLogger(__name__)


class SMSInboxInput(WebhookInput):
    """Same delivery path as WebhookInput; normalizes Teltonika shape
    if recognized."""

    kind = "sms_inbox"

    @property
    def topic(self) -> str:
        return f"sms_inbox:{self.name}"

    async def deliver(self, payload: Any) -> None:
        """Optionally normalize before delivering. Teltonika's shape
        is already friendly — we just rename a few fields for
        consistency with our convention."""
        normalized = _normalize(payload)
        self._last_msg_ts = time.time()
        self._msg_count += 1
        try:
            await self.on_value(self.topic, normalized, "sms_inbox")
        except Exception as e:
            self._last_error = f"{type(e).__name__}: {e}"[:200]
            raise


def _normalize(payload: Any) -> dict[str, Any]:
    """Map Teltonika field names to our canonical schema.

    Canonical:
      - ``from`` (str): sender phone in E.164
      - ``body`` (str): message text
      - ``received_at`` (str): ISO 8601
      - ``modem`` (str): optional modem id
      - ``raw`` (dict): the original payload
    """
    if not isinstance(payload, dict):
        return {"body": str(payload), "raw": payload}

    out = {
        "from": payload.get("from") or payload.get("sender") or payload.get("number"),
        "body": payload.get("body") or payload.get("message") or payload.get("text"),
        "received_at": payload.get("received_at") or payload.get("timestamp") or payload.get("ts"),
        "modem": payload.get("modem") or payload.get("device"),
        "raw": payload,
    }
    return out
