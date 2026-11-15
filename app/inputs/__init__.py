"""Input adapters — pluggable sources of values.

Public surface:

    from app.inputs import REGISTRY, BaseInput, MQTTSubscriber

The registry maps ``kind`` → adapter class. Adding a new kind is a
plug-in change documented in ``docs/EXTENSIBILITY.md``.
"""
from __future__ import annotations

from .alertmanager import AlertmanagerInput
from .base import BaseInput, ValueCallback
from .http_poll import HTTPPollInput
from .mqtt import MQTTSubscriber
from .sms_inbox import SMSInboxInput
from .webhook import WebhookInput

REGISTRY: dict[str, type[BaseInput]] = {
    "mqtt": MQTTSubscriber,
    "http_poll": HTTPPollInput,
    "webhook": WebhookInput,
    "sms_inbox": SMSInboxInput,
    "alertmanager": AlertmanagerInput,
    # Future: schedule, email_imap
}


__all__ = [
    "BaseInput", "ValueCallback", "MQTTSubscriber", "HTTPPollInput",
    "WebhookInput", "SMSInboxInput", "AlertmanagerInput", "REGISTRY",
]
