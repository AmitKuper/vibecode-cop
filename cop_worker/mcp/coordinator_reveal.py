"""Inbound reveal guarding, final-audit guard, and state queries (mixin)."""

from __future__ import annotations

import logging

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
from cop_worker.mcp.coordinator_records import _IdempotencyRecord, _reveal_content_key
from cop_worker.mcp.protocol import ProtocolState

logger = logging.getLogger(__name__)


class CoordinatorRevealMixin:
    """Reveal advancement, final-audit guard, and read-side queries."""

    def check_and_advance_inbound_reveal(
        self,
        game_id: str,
        gamelet: int,
        role: str,
        step: int,
        move: str,
        hint: str | None = None,
        intent: str | None = None,
        state_hash: str | None = None,
    ) -> tuple[bool, str | None, dict | None, ProtocolState | None]:
        """Guard and advance SM for an inbound REVEAL.

        Same return contract as check_and_advance_inbound_commit.
        Idempotency is now keyed on the full reveal payload hash (move + hint +
        intent + state_hash) so that a replay with altered fields is detected.
        """
        content_key = _reveal_content_key(move, hint, intent, state_hash)
        ikey = (game_id, gamelet, role, step, "reveal")
        with self._idempotency_lock:
            rec = self._idempotency.get(ikey)
        if rec is not None:
            if rec.content_key == content_key:
                return True, None, {**rec.cached_response, "idempotent": True}, None
            return (
                False,
                f"Conflicting reveal at step {step}: payload mismatch",
                None,
                None,
            )

        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            # Fix 5: Enforce monotonically increasing step numbers for reveal
            if step <= entry.last_accepted_reveal_step:
                last = entry.last_accepted_reveal_step
                return (
                    False,
                    f"Out-of-order reveal: step {step} not greater than last accepted {last}",
                    None,
                    None,
                )
            ok, err = sm.guard_reveal_received()
            if not ok:
                return False, err, None, None
            prev_state = sm.state
            next_state = (
                ProtocolState.STEP_VERIFIED
                if sm.state == ProtocolState.REVEAL_SENT
                else ProtocolState.REVEAL_RECEIVED
            )
            sm.transition(next_state)
            # Record the accepted reveal step
            entry.last_accepted_reveal_step = step
            return True, None, None, prev_state

    def rollback_inbound_reveal(
        self, game_id: str, gamelet: int, role: str, prev_state: ProtocolState
    ) -> None:
        """Roll back an inbound reveal advance if the callback failed."""
        entry = self._registry.get(game_id, gamelet, role)
        if entry is None:
            return
        with entry.lock:
            # Also revert the last_accepted_reveal_step counter on rollback
            if entry.last_accepted_reveal_step > -1:
                entry.last_accepted_reveal_step -= 1
            entry.sm.state = prev_state
            logger.warning(
                "[Coordinator] Rolled back reveal for %s → %s", game_id, prev_state.value
            )

    def record_reveal_response(
        self,
        game_id: str,
        gamelet: int,
        role: str,
        step: int,
        move: str,
        response: dict,
        hint: str | None = None,
        intent: str | None = None,
        state_hash: str | None = None,
    ) -> None:
        """Store the successful response for an inbound reveal (for idempotency)."""
        ikey = (game_id, gamelet, role, step, "reveal")
        content_key = _reveal_content_key(move, hint, intent, state_hash)
        with self._idempotency_lock:
            self._idempotency[ikey] = _IdempotencyRecord(content_key, response)
