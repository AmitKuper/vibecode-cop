"""Per-session protocol state tracking with per-game concurrency locks.

Each game session is identified by (game_id, gamelet_num, local_role).
A threading.Lock() per session ensures that concurrent inbound MCP calls
for the same session are serialized before any state mutation.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from cop_worker.mcp.protocol import ProtocolState, ProtocolStateMachine

# (game_id, gamelet_num, local_role) → SessionEntry
SessionKey = tuple[str, int, str]


@dataclass
class SessionEntry:
    sm: ProtocolStateMachine = field(default_factory=ProtocolStateMachine)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Tracks whether WE have sent our commit/reveal this step (so we can
    # detect duplicate sends or help the state machine know which transition
    # to fire when a peer message arrives).
    commit_sent_step: int = -1
    reveal_sent_step: int = -1

    # Fix 5: Track the last accepted inbound step number for commit and reveal.
    # Initialized to -1 (no steps accepted yet). Any commit/reveal with
    # step <= last_accepted_* is rejected as an out-of-order or replay message.
    last_accepted_commit_step: int = -1
    last_accepted_reveal_step: int = -1


class SessionRegistry:
    """Thread-safe registry of per-session state machines."""

    def __init__(self) -> None:
        self._sessions: dict[SessionKey, SessionEntry] = {}
        self._registry_lock = threading.Lock()

    def get_or_create(self, game_id: str, gamelet: int, role: str) -> SessionEntry:
        """Return existing or fresh SessionEntry for the given key."""
        key: SessionKey = (game_id, gamelet, role)
        with self._registry_lock:
            if key not in self._sessions:
                self._sessions[key] = SessionEntry()
            return self._sessions[key]

    def get(self, game_id: str, gamelet: int, role: str) -> SessionEntry | None:
        """Return existing SessionEntry or None."""
        key: SessionKey = (game_id, gamelet, role)
        with self._registry_lock:
            return self._sessions.get(key)

    def remove(self, game_id: str, gamelet: int, role: str) -> None:
        """Remove a session entry (called after DONE/ABORTED)."""
        key: SessionKey = (game_id, gamelet, role)
        with self._registry_lock:
            self._sessions.pop(key, None)

    def state_of(self, game_id: str, gamelet: int, role: str) -> ProtocolState | None:
        """Convenience: current state for a session or None if not tracked."""
        entry = self.get(game_id, gamelet, role)
        return entry.sm.state if entry else None

    def all_keys(self) -> list[SessionKey]:
        with self._registry_lock:
            return list(self._sessions.keys())


# Module-level singleton — imported by server_handlers
_registry = SessionRegistry()


def get_registry() -> SessionRegistry:
    return _registry
