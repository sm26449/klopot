"""How many failed authentications an address may make in a window.

One instance per credential kind — API keys (app/auth.py) and inbound input
tokens (app/api/v1/inputs.py) — so a sender with a stale input token does not
lock the API keys used from the same address out, and the reverse.

- **Per address**, IPv6 by its /64 (a client gets a whole /64: one budget per
  /128 would be one per request); an IPv4-mapped IPv6 address is its IPv4.
- **Bounded memory**: at most ``max_addresses`` are tracked; the one that
  failed longest ago makes room, in O(1) (review K15 — a full rebuild of
  10,000 entries per new address blocked the loop ~3 ms a request).
- **Reserve, then refund**: a caller that must check the budget before a
  slow verification counts the failure first (``note``) and takes it back
  (``refund``) if it was not one, so a concurrent burst cannot all pass the
  check before any is recorded (review K15).

Synchronous and in process (Klopot runs one worker).
"""
from __future__ import annotations

import ipaddress
import time
from collections import OrderedDict
from collections.abc import Callable


def address_unit(ip: str) -> str:
    """The unit a budget is kept for: the address, or its /64 for IPv6."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


class FailureBudget:
    """``max_failures`` per ``window_sec`` for each address (see the module
    docstring). Without an address nothing is counted and nothing is spent."""

    def __init__(self, *, max_failures: int, window_sec: float, max_addresses: int,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.max_failures = max_failures
        self.window_sec = window_sec
        self.max_addresses = max_addresses
        self._clock = clock
        # Insertion-ordered by the last failure: the front failed longest ago.
        self._failures: OrderedDict[str, list[float]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._failures)

    def __contains__(self, ip: object) -> bool:
        return isinstance(ip, str) and address_unit(ip) in self._failures

    @property
    def retry_after(self) -> int:
        """Seconds a refused address should wait: the whole window."""
        return int(self.window_sec)

    def count(self, ip: str | None) -> int:
        """Failures of ``ip`` within the window."""
        return len(self._recent(address_unit(ip), self._clock())) if ip else 0

    def spent(self, ip: str | None) -> bool:
        return self.count(ip) >= self.max_failures

    def note(self, ip: str | None) -> None:
        if not ip:
            return
        unit, now = address_unit(ip), self._clock()
        recent = self._recent(unit, now)
        if unit not in self._failures:
            while len(self._failures) >= self.max_addresses:
                self._failures.popitem(last=False)
        self._failures[unit] = [*recent, now]
        self._failures.move_to_end(unit)

    def refund(self, ip: str | None) -> None:
        """Take back the last failure noted for ``ip``."""
        if not ip:
            return
        unit = address_unit(ip)
        stamps = self._failures.get(unit)
        if stamps:
            stamps.pop()
            if not stamps:
                self._failures.pop(unit, None)

    def reset(self) -> None:
        self._failures.clear()

    def _recent(self, unit: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(unit, ()) if now - t < self.window_sec]
        if recent:
            self._failures[unit] = recent
        else:
            self._failures.pop(unit, None)
        return recent
