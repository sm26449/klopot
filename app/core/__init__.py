"""Core domain — state cache, engine, dispatcher, eval, rendering.

Public surface used by api/ and inputs/:

    from app.core import state_cache, manager

The engine that ticks rules + dispatcher land in S4. S3 ships the
foundation (state cache + variable resolver + input manager).
"""
from __future__ import annotations
