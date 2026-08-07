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

import contextlib
import hashlib
import logging
import threading
import time
from dataclasses import dataclass

from cop_worker.mcp.protocol import ProtocolState
from cop_worker.mcp.session_registry import SessionRegistry, get_registry
from cop_worker.reliability.durable_io import atomic_write_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _reveal_content_key(
    move: str,
    hint: str | None = None,
    intent: str | None = None,
    state_hash: str | None = None,
) -> str:
    """Compute a canonical SHA-256 hash over the full reveal payload.

    This ensures idempotency is keyed on all mutable fields, not just move,
    so a replay that alters hint/intent/state_hash is detected as a conflict.
    """
    from cop_worker.crypto import canonical_json

    payload = {
        "move": move,
        "hint": hint or "",
        "intent": intent or "",
        "state_hash": state_hash or "",
    }
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Idempotency record
# ---------------------------------------------------------------------------


@dataclass
class _IdempotencyRecord:
    content_key: str  # h_commit for commits, full-payload hash for reveals
    cached_response: dict


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class ProtocolCoordinator:
    """Single authority for protocol state machine transitions.

    One instance per process (the module singleton returned by get_coordinator).
    Tests may create isolated instances via ProtocolCoordinator(registry=...).
    """

    def __init__(self, registry: SessionRegistry | None = None) -> None:
        self._registry: SessionRegistry = registry or get_registry()
        # Idempotency cache: (game_id, gamelet, role, step, phase) → _IdempotencyRecord
        self._idempotency: dict[tuple, _IdempotencyRecord] = {}
        self._idempotency_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Handshake
    # ------------------------------------------------------------------

    def on_handshake_complete(self, game_id: str, gamelet: int, role: str) -> None:
        """Advance local SM to READY after start_game is successfully sent or received.

        Idempotent: if already READY, does nothing.
        """
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.READY:
                return  # Already done (idempotent)
            if sm.state not in (ProtocolState.IDLE, ProtocolState.STEP0_NEGOTIATING):
                logger.warning(
                    "[Coordinator] on_handshake_complete called in state %s for %s",
                    sm.state.value,
                    game_id,
                )
                return
            if sm.state == ProtocolState.IDLE:
                sm.transition(ProtocolState.STEP0_NEGOTIATING)
            sm.transition(ProtocolState.READY)
            logger.info(
                "[Coordinator] Handshake complete → READY for %s gamelet=%d %s",
                game_id,
                gamelet,
                role,
            )

    # ------------------------------------------------------------------
    # Outbound lifecycle (active / cop side)
    # ------------------------------------------------------------------

    def begin_step(self, game_id: str, gamelet: int, role: str, step: int) -> None:
        """Advance READY or STEP_VERIFIED → COMPUTING_MOVE at start of a step.

        No-op if already in COMPUTING_MOVE or a terminal state.
        """
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state in (ProtocolState.READY, ProtocolState.STEP_VERIFIED):
                if sm.state == ProtocolState.STEP_VERIFIED:
                    sm.advance_step()
                sm.transition(ProtocolState.COMPUTING_MOVE)
                logger.debug("[Coordinator] begin_step %s step=%d → COMPUTING_MOVE", game_id, step)

    def on_commit_exchange_complete(self, game_id: str, gamelet: int, role: str, step: int) -> None:
        """Advance COMPUTING_MOVE → COMMIT_SENT → BOTH_COMMITTED.

        Called after a synchronous commit exchange where we send our commit and
        the peer immediately returns their commit in the same HTTP response.
        """
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.COMPUTING_MOVE:
                sm.transition(ProtocolState.COMMIT_SENT)
                sm.transition(ProtocolState.BOTH_COMMITTED)
                entry.commit_sent_step = step
                logger.debug(
                    "[Coordinator] commit_exchange_complete %s step=%d → BOTH_COMMITTED",
                    game_id,
                    step,
                )
            elif sm.state == ProtocolState.COMMIT_RECEIVED:
                # Peer committed first; we just sent ours
                sm.transition(ProtocolState.BOTH_COMMITTED)
                entry.commit_sent_step = step
            elif sm.state == ProtocolState.BOTH_COMMITTED:
                pass  # idempotent
            else:
                logger.warning(
                    "[Coordinator] on_commit_exchange_complete: unexpected state %s", sm.state.value
                )

    def on_reveal_exchange_complete(self, game_id: str, gamelet: int, role: str, step: int) -> None:
        """Advance BOTH_COMMITTED → REVEAL_SENT → STEP_VERIFIED."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.BOTH_COMMITTED:
                sm.transition(ProtocolState.REVEAL_SENT)
                sm.transition(ProtocolState.STEP_VERIFIED)
                entry.reveal_sent_step = step
                logger.debug(
                    "[Coordinator] reveal_exchange_complete %s step=%d → STEP_VERIFIED",
                    game_id,
                    step,
                )
            elif sm.state == ProtocolState.REVEAL_RECEIVED:
                sm.transition(ProtocolState.STEP_VERIFIED)
                entry.reveal_sent_step = step
            elif sm.state == ProtocolState.STEP_VERIFIED:
                pass  # idempotent

    def on_audit_begin(self, game_id: str, gamelet: int, role: str) -> None:
        """Advance STEP_VERIFIED → AUDITING."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.STEP_VERIFIED:
                sm.transition(ProtocolState.AUDITING)

    def on_final_audit_complete(self, game_id: str, gamelet: int, role: str) -> None:
        """Advance AUDITING → RESULT_AGREEMENT."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.AUDITING:
                sm.transition(ProtocolState.RESULT_AGREEMENT)

    def on_done(self, game_id: str, gamelet: int, role: str) -> None:
        """Advance RESULT_AGREEMENT → REPORTING → DONE."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.RESULT_AGREEMENT:
                sm.transition(ProtocolState.REPORTING)
            if sm.state == ProtocolState.REPORTING:
                sm.transition(ProtocolState.DONE)

    def on_technical_loss(
        self,
        game_id: str,
        gamelet: int,
        role: str,
        reason: str = "",
        evidence: dict | None = None,
        evidence_path: str | None = None,
    ) -> None:
        """Advance to TECHNICAL_LOSS and durably record the controlled outcome."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock, contextlib.suppress(ValueError):
            entry.sm.transition(ProtocolState.TECHNICAL_LOSS)
        if evidence_path:
            atomic_write_json(
                evidence_path,
                {
                    "schema_version": "1.0",
                    "game_id": game_id,
                    "gamelet": gamelet,
                    "role": role,
                    "protocol_state": ProtocolState.TECHNICAL_LOSS.value,
                    "reason": reason,
                    "evidence": evidence or {},
                    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
        if reason:
            logger.error(
                "[Coordinator] TECHNICAL_LOSS %s gamelet=%d %s: %s evidence=%s",
                game_id,
                gamelet,
                role,
                reason,
                evidence,
            )

    def cleanup_session(self, game_id: str, gamelet: int, role: str) -> None:
        """Remove session from registry after it reaches a terminal state.

        Terminal states: DONE, ABORTED, TECHNICAL_LOSS.
        Idempotent: if the session does not exist, does nothing.
        """
        state = self._registry.state_of(game_id, gamelet, role)
        if state in (
            ProtocolState.DONE,
            ProtocolState.TECHNICAL_LOSS,
            ProtocolState.ABORTED,
            None,
        ):
            self._registry.remove(game_id, gamelet, role)
            # Also purge idempotency records for this session to free memory
            with self._idempotency_lock:
                keys_to_remove = [
                    k
                    for k in self._idempotency
                    if k[0] == game_id and k[1] == gamelet and k[2] == role
                ]
                for k in keys_to_remove:
                    del self._idempotency[k]
            logger.info(
                "[Coordinator] Session cleaned up: %s gamelet=%d %s (state was %s)",
                game_id,
                gamelet,
                role,
                state.value if state else "None",
            )
        else:
            logger.warning(
                "[Coordinator] cleanup_session called but state is %s (non-terminal) for %s",
                state.value if state else "None",
                game_id,
            )

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


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_coordinator = ProtocolCoordinator()


def get_coordinator() -> ProtocolCoordinator:
    """Return the process-wide ProtocolCoordinator singleton."""
    return _coordinator
