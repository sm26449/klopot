"""Output channel adapters (plug-in).

Each kind (ui, banner, telegram, sms, email, push, webhook) is a
plug-in declared in ``registry.py``. Adding a kind is documented in
``docs/EXTENSIBILITY.md``.

Public surface:

    from app.channels import REGISTRY, BaseChannel, Notification
    from app.channels.manager import get_channel_manager
"""
from __future__ import annotations

from .base import BaseChannel, Notification, SendResult
from .registry import REGISTRY

__all__ = ["BaseChannel", "Notification", "SendResult", "REGISTRY"]
