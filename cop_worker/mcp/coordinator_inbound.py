"""Inbound commit/reveal guarding, idempotency, and rollback (mixin)."""

from __future__ import annotations

import logging

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
from cop_worker.mcp.coordinator_records import _IdempotencyRecord
from cop_worker.mcp.protocol import ProtocolState

logger = logging.getLogger(__name__)


class CoordinatorInboundMixin:
    """Transactional inbound-message advancement with idempotency cache."""

    # ------------------------------------------------------------------
    # Passive-side post-callback advances (thief side)
    # ------------------------------------------------------------------

    def on_passive_commit_sent(
        self, game_id: str, gamelet: int, role: str, step: int, h_commit: str
    ) -> None:
        """Advance COMMIT_RECEIVED → BOTH_COMMITTED after passive side sends its commit.

        The passive side (thief) returns its commit in the HTTP response body,
        not via a separate outbound call.  This method records that fact.
        """
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.COMMIT_RECEIVED:
                sm.transition(ProtocolState.BOTH_COMMITTED)
                entry.commit_sent_step = step
                logger.debug(
                    "[Coordinator] passive commit_sent %s step=%d → BOTH_COMMITTED", game_id, step
                )

    def on_passive_reveal_sent(
        self, game_id: str, gamelet: int, role: str, step: int, move: str
    ) -> None:
        """Advance REVEAL_RECEIVED → STEP_VERIFIED after passive side sends its reveal."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.REVEAL_RECEIVED:
                sm.transition(ProtocolState.STEP_VERIFIED)
                entry.reveal_sent_step = step
                logger.debug(
                    "[Coordinator] passive reveal_sent %s step=%d → STEP_VERIFIED", game_id, step
                )

    # ------------------------------------------------------------------
    # Inbound guard + advance (called by server_handlers)
    # ------------------------------------------------------------------

    def check_and_advance_inbound_commit(
        self, game_id: str, gamelet: int, role: str, step: int, h_commit: str
    ) -> tuple[bool, str | None, dict | None, ProtocolState | None]:
        """Guard and advance SM for an inbound COMMIT.

        Returns (ok, error_str, cached_response, prev_state):
          - If exact duplicate: ok=True, error=None, cached_response=<dict>, prev_state=None
          - If conflicting duplicate: ok=False, error=<msg>, cached_response=None, prev_state=None
          - If SM rejection: ok=False, error=<msg>, cached_response=None, prev_state=None
          - On success: ok=True, error=None, cached_response=None, prev_state=<state before advance>

        prev_state is returned so the caller can rollback if the callback fails.
        """
        ikey = (game_id, gamelet, role, step, "commit")
        with self._idempotency_lock:
            rec = self._idempotency.get(ikey)
        if rec is not None:
            if rec.content_key == h_commit:
                logger.debug("[Coordinator] idempotent commit %s step=%d", game_id, step)
                return True, None, {**rec.cached_response, "idempotent": True}, None
            return (
                False,
                f"Conflicting commit at step {step}: h_commit mismatch",
                None,
                None,
            )

        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            # Fix 5: Enforce monotonically increasing step numbers to prevent replay.
            # Any commit with step <= last_accepted is a replay or out-of-order message.
            if step <= entry.last_accepted_commit_step:
                last = entry.last_accepted_commit_step
                return (
                    False,
                    f"Out-of-order commit: step {step} not greater than last accepted {last}",
                    None,
                    None,
                )
            # Save state BEFORE any auto-transition for rollback purposes
            prev_state = sm.state
            # Accept READY / STEP_VERIFIED → auto-advance to COMPUTING_MOVE (passive side)
            if sm.state in (ProtocolState.READY, ProtocolState.STEP_VERIFIED):
                if sm.state == ProtocolState.STEP_VERIFIED:
                    sm.advance_step()
                sm.transition(ProtocolState.COMPUTING_MOVE)
            ok, err = sm.guard_commit_received()
            if not ok:
                return False, err, None, None
            next_state = (
                ProtocolState.BOTH_COMMITTED
                if sm.state == ProtocolState.COMMIT_SENT
                else ProtocolState.COMMIT_RECEIVED
            )
            sm.transition(next_state)
            # Record the accepted step; future commits must use a higher step
            entry.last_accepted_commit_step = step
            return True, None, None, prev_state

    def rollback_inbound_commit(
        self, game_id: str, gamelet: int, role: str, prev_state: ProtocolState
    ) -> None:
        """Roll back an inbound commit advance if the callback failed."""
        entry = self._registry.get(game_id, gamelet, role)
        if entry is None:
            return
        with entry.lock:
            # Also revert the last_accepted_commit_step counter on rollback
            if entry.last_accepted_commit_step > -1:
                entry.last_accepted_commit_step -= 1
            entry.sm.state = prev_state
            logger.warning(
                "[Coordinator] Rolled back commit for %s → %s", game_id, prev_state.value
            )

    def record_commit_response(
        self, game_id: str, gamelet: int, role: str, step: int, h_commit: str, response: dict
    ) -> None:
        """Store the successful response for an inbound commit (for idempotency)."""
        ikey = (game_id, gamelet, role, step, "commit")
        with self._idempotency_lock:
            self._idempotency[ikey] = _IdempotencyRecord(h_commit, response)
