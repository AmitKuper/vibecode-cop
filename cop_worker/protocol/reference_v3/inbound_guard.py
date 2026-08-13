"""Inbound request-rate guard for the reference-v3 tool surface (DOS detection).

Appendix E rule 29 requires detecting a flooding peer, not only pacing our own
sends. The guard is deliberately generous — the ceiling sits far above any real
peer's retry cadence (an eager opponent re-dialing greetings every second stays
two orders of magnitude below it) — so it can only ever trip on a genuine flood.
A tripped guard REFUSES the call with a structured error and touches no session
state; it never terminates the game (the series loop owns those decisions).
"""

from __future__ import annotations

import time
from collections import deque

#: Sliding-window ceiling: inbound tool calls per minute before refusal.
MAX_CALLS_PER_MINUTE = 300


class InboundGuard:
    """Sliding one-minute window over inbound tool-call timestamps."""

    def __init__(self, max_per_minute: int = MAX_CALLS_PER_MINUTE) -> None:
        self.max_per_minute = int(max_per_minute)
        self._stamps: deque[float] = deque()
        self.refused = 0  # observability: how many calls the guard turned away

    def allow(self) -> bool:
        """Record one call; True if within the ceiling, False on flood."""
        now = time.monotonic()
        window_start = now - 60.0
        while self._stamps and self._stamps[0] < window_start:
            self._stamps.popleft()
        if len(self._stamps) >= self.max_per_minute:
            self.refused += 1
            return False
        self._stamps.append(now)
        return True
