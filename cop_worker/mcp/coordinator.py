"""ProtocolCoordinator — single authority for all protocol state transitions.

All inbound (server_handlers) and outbound (peer_turn_loop) state machine
mutations route through this class.  Direct mutations to ProtocolStateMachine
outside this coordinator are forbidden.

Idempotency model
-----------------
Each (game_id, gamelet, role, step, phase) tuple may be processed at most once.
An EXACT duplicate (same content key) returns the cached response immediately
without re-invoking the callback.  A CONFLICTING duplicate (same position, different
content) is a protocol violation and returns an error.

Transactional callbacks
-----------------------
The SM is advanced under entry.lock BEFORE the callback executes.  If the
callback raises an exception, the SM is rolled back to its pre-call state under
the lock, and technical_loss is NOT triggered automatically (caller decides).
"""

from __future__ import annotations

import logging
import threading

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
from cop_worker.mcp.coordinator_inbound import CoordinatorInboundMixin
from cop_worker.mcp.coordinator_lifecycle import CoordinatorLifecycleMixin
from cop_worker.mcp.coordinator_queries import CoordinatorQueriesMixin
from cop_worker.mcp.coordinator_records import (  # noqa: F401  (re-exports)
    _IdempotencyRecord,
    _reveal_content_key,
)
from cop_worker.mcp.coordinator_reveal import CoordinatorRevealMixin
from cop_worker.mcp.coordinator_terminal import CoordinatorTerminalMixin
from cop_worker.mcp.session_registry import SessionRegistry, get_registry

logger = logging.getLogger(__name__)


def gamelet_from_game_id(game_id: str, *, strict: bool = False) -> int:
    """Extract gamelet number from '<uuid>_g<N>' format.

    In strict mode, raises ValueError if the ID does not have a valid '_gN'
    suffix.  In non-strict mode (default), falls back to 0 so that legacy
    IDs without a suffix continue to work.
    """
    parts = game_id.rsplit("_g", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    if strict:
        raise ValueError(f"game_id {game_id!r} has no valid '_gN' suffix (strict mode)")
    return 0


class ProtocolCoordinator(
    CoordinatorLifecycleMixin,
    CoordinatorTerminalMixin,
    CoordinatorInboundMixin,
    CoordinatorRevealMixin,
    CoordinatorQueriesMixin,
):
    """Single authority for protocol state machine transitions.

    One instance per process (the module singleton returned by get_coordinator).
    Tests may create isolated instances via ProtocolCoordinator(registry=...).
    """

    def __init__(self, registry: SessionRegistry | None = None) -> None:
        self._registry: SessionRegistry = registry or get_registry()
        # Idempotency cache: (game_id, gamelet, role, step, phase) → _IdempotencyRecord
        self._idempotency: dict[tuple, _IdempotencyRecord] = {}
        self._idempotency_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_coordinator = ProtocolCoordinator()


def get_coordinator() -> ProtocolCoordinator:
    """Return the process-wide ProtocolCoordinator singleton."""
    return _coordinator
