"""Channel kind → adapter class mapping.

Adding a new kind: implement the adapter, register here, declare in
``app/schemas/common.py:ChannelKind`` enum, add to
``app/db/models.py:ChannelKind`` enum, write the migration.
"""
from __future__ import annotations

from .base import BaseChannel
from .email import EmailChannel
from .gotify import GotifyChannel
from .mqtt import MQTTChannel
from .ntfy import NtfyChannel
from .push import PushChannel
from .pushover import PushoverChannel
from .sms import SMSChannel
from .telegram import TelegramChannel
from .ui import UIChannel
from .webhook import WebhookChannel

REGISTRY: dict[str, type[BaseChannel]] = {
    "ui": UIChannel,
    "telegram": TelegramChannel,
    "sms": SMSChannel,
    # banner: same as ui for now (UI handles banners client-side)
    "banner": UIChannel,
    "email": EmailChannel,
    "push": PushChannel,
    "webhook": WebhookChannel,
    "mqtt": MQTTChannel,
    "ntfy": NtfyChannel,
    "gotify": GotifyChannel,
    "pushover": PushoverChannel,
}

__all__ = ["REGISTRY"]
