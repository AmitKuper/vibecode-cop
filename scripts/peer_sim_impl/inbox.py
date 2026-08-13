"""Shared inbound-message store for the peersim single-port server.

Everything vibecode's outbound calls deliver (greetings, turns, audits,
controls) lands here; the client-side window loops poll it. Single event loop,
so plain containers with async polling are race-free.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque


class PeerInbox:
    """Inbound state for all six windows (the server is one URL, like najamjad)."""

    def __init__(self) -> None:
        self.greetings: dict[int, dict] = {}  # sub_game_number -> latest greeting
        self.turns: list[dict] = []
        self.audits: deque[dict] = deque()
        self.controls: deque[dict] = deque()

    def reset_window(self) -> None:
        """Drop stale settle traffic at window start. Turns are NOT cleared here:
        vibecode (fed by the eager-greeting relay) can handshake and send its
        first turn for window N while we are still slow-dialing — a start-of-
        window wipe eats that turn and deadlocks the window (live bench finding,
        2026-08-13). Turns are purged by sender at window END instead."""
        self.audits.clear()
        self.controls.clear()

    def purge_sender(self, sender: str) -> None:
        """End-of-window cleanup: remove the played opponent's turns so a later
        window with the same sender cannot match its stale steps. The other
        sender's early next-window turns survive."""
        self.turns[:] = [t for t in self.turns if t.get("sender") != sender]

    def add_greeting(self, message: dict) -> None:
        n = message.get("sub_game_number")
        if isinstance(n, int):
            self.greetings[n] = dict(message)

    def latest_turn(self, sender: str, step: int) -> dict | None:
        for turn in reversed(self.turns):
            if turn.get("sender") == sender and turn.get("step") == step:
                return turn
        return None

    async def wait_greeting(self, sub_game: int, *, timeout: float) -> dict:
        """Return AND CONSUME the greeting for ``sub_game`` (a vibecode index-hold
        retry re-sends a fresh one, so consuming keeps retries in lock-step)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if sub_game in self.greetings:
                return self.greetings.pop(sub_game)
            await asyncio.sleep(0.1)
        raise TimeoutError(f"no vibecode greeting for window {sub_game} within {timeout:.0f}s")

    async def wait_turn(self, sender: str, step: int, *, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            turn = self.latest_turn(sender, step)
            if turn is not None:
                return turn
            await asyncio.sleep(0.05)
        raise TimeoutError(f"no inbound {sender} turn step {step} within {timeout:.0f}s")

    async def wait_audit(self, *, timeout: float) -> dict | None:
        """Best-effort wait for vibecode's audit (None on timeout — never fatal)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.audits:
                return self.audits.popleft()
            await asyncio.sleep(0.1)
        return None
