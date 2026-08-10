"""Final-audit guard and read-side state queries (mixin)."""

from __future__ import annotations

import logging

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
from cop_worker.mcp.protocol import ProtocolState

logger = logging.getLogger(__name__)


class CoordinatorQueriesMixin:
    """Final-audit guard, state lookup, idempotency snapshot, readiness."""

    def check_final_audit_guard(
        self, game_id: str, gamelet: int, role: str
    ) -> tuple[bool, str | None, ProtocolState | None]:
        """Guard and advance SM for an inbound FINAL_AUDIT."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            # Accept STEP_VERIFIED → auto-advance to AUDITING
            if sm.state == ProtocolState.STEP_VERIFIED:
                sm.transition(ProtocolState.AUDITING)
            ok, err = sm.guard_final_audit_received()
            if not ok:
                return False, err, None
            prev_state = sm.state
            sm.transition(ProtocolState.RESULT_AGREEMENT)
            return True, None, prev_state

    # ------------------------------------------------------------------
    # State inspection
    # ------------------------------------------------------------------

    def get_state(self, game_id: str, gamelet: int, role: str) -> ProtocolState | None:
        """Current SM state for the session, or None if no session exists."""
        return self._registry.state_of(game_id, gamelet, role)

    def snapshot_idempotency(self, game_id: str, gamelet: int, role: str) -> dict:
        """Return a JSON-safe recovery snapshot of one session's response cache."""
        with self._idempotency_lock:
            return {
                "|".join(str(part) for part in key): {
                    "content_key": record.content_key,
                    "cached_response": record.cached_response,
                }
                for key, record in self._idempotency.items()
                if key[:3] == (game_id, gamelet, role)
            }

    def is_ready(self, game_id: str, gamelet: int, role: str) -> bool:
        """Return True if the session is in an active gameplay state.

        Returns True only when the session is in a state where gameplay can
        proceed (post-handshake, pre-terminal).  Returns False for IDLE,
        STEP0_NEGOTIATING, DONE, TECHNICAL_LOSS, and ABORTED.
        """
        state = self.get_state(game_id, gamelet, role)
        return state is not None and state in (
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.COMMIT_RECEIVED,
            ProtocolState.BOTH_COMMITTED,
            ProtocolState.REVEAL_SENT,
            ProtocolState.REVEAL_RECEIVED,
            ProtocolState.STEP_VERIFIED,
            ProtocolState.AUDITING,
            ProtocolState.RESULT_AGREEMENT,
            ProtocolState.REPORTING,
        )
