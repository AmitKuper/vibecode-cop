"""Gamelet inbound event handling: turn, audit, control (mixin)."""

from __future__ import annotations

import logging

from cop_worker.commit_reveal import CommitRevealStateMachine, ProtocolViolationError
from cop_worker.state_machine import GameletState

logger = logging.getLogger(__name__)


class GameletEventMixin:
    """Inbound turn/audit/control processing."""

    def _handle_turn(self, payload: dict) -> dict:
        """Process an opponent turn event and return our response.

        On commit: ACK opponent's commit and include our own commit in the response.
        On reveal: verify opponent's reveal and send our own reveal.

        Args:
            payload: Raw turn payload dict.

        Returns:
            Response dict with ok, response_payload, and state.
        """
        if self._sm.state != GameletState.PLAYING:
            raise ProtocolViolationError(f"turn in state {self._sm.state}")
        turn = self._processor.normalise_turn(payload)
        if turn.kind == "commit":
            # Accept opponent's commit with a fresh per-step CR instance
            step_cr = CommitRevealStateMachine(expected_step=turn.step)
            step_cr.receive_commit(turn.step, turn.commitment_hash)
            # Store opponent's hash for later verify_reveal
            if not hasattr(self, "_opponent_commits"):
                self._opponent_commits: dict[int, str] = {}
            self._opponent_commits[turn.step] = turn.commitment_hash
            self._step = turn.step
            # Absorb the opponent's transmitted scent + hint so the move we generate below
            # observes where the opponent actually is (was previously an all-zero field).
            if turn.smell_grid is not None:
                self._opponent_smell = turn.smell_grid
            if turn.hint:
                self._last_hint = turn.hint
            # Also advance the primary CR if it's for the expected step
            if self._cr is not None and self._cr._expected_step == turn.step:
                import contextlib

                with contextlib.suppress(Exception):
                    self._cr.receive_commit(turn.step, turn.commitment_hash)
            # Generate our own commitment for this step (obs built from current position +
            # the opponent scent just absorbed), then advance our own tracked position and
            # emit our book scent field so the opponent can smell us next turn.
            our_action = self._generate_move()
            self._advance_own(our_action, turn.step)
            own_smell = self._own_smell_grid()
            our_nonce, our_commitment = self._generate_commitment(our_action)
            self._pending_reveals[turn.step] = (our_nonce, our_action)
            return {
                "ok": True,
                "response_payload": {
                    "kind": "commit",
                    "step": turn.step,
                    "commitment_hash": our_commitment,
                    "smell_grid": own_smell,
                },
                "state": self._sm.state,
            }
        if turn.kind == "reveal":
            # Verify opponent's reveal against stored commitment hash
            stored_hash = (
                self._opponent_commits.get(turn.step)
                if hasattr(self, "_opponent_commits")
                else None
            )
            verified = False
            if stored_hash is not None and turn.nonce is not None and turn.action is not None:
                try:
                    verified = CommitRevealStateMachine(expected_step=turn.step).verify_reveal(
                        stored_hash, turn.nonce, turn.action
                    )
                except Exception:
                    verified = False
            # Send our own reveal for this step
            our_nonce, our_action = self._pending_reveals.pop(turn.step, (None, None))
            return {
                "ok": True,
                "response_payload": {
                    "kind": "reveal",
                    "step": turn.step,
                    "nonce": our_nonce,
                    "action": our_action,
                    "opponent_verified": verified,
                },
                "state": self._sm.state,
            }
        return {"ok": True, "response_payload": {"ack": True}, "state": self._sm.state}

    def _handle_audit(self, payload: dict) -> dict:
        """Process opponent's audit submission. Transitions AUDITING -> VERIFIED -> SETTLED.

        Args:
            payload: Raw audit payload dict.

        Returns:
            Response dict with ok and state.
        """
        self._processor.normalise_audit(payload)
        self._sm.transition(GameletState.VERIFIED)
        self._sm.transition(GameletState.SETTLED)
        self._result = self._build_result(audit_ok=True)
        return {"ok": True, "state": self._sm.state}

    def _handle_control(self, payload: dict) -> dict:
        """Process a control signal.

        Args:
            payload: Raw control payload dict.

        Returns:
            Response dict with ok and state.
        """
        msg = self._processor.normalise_control(payload)
        logger.info("Control signal: %s reason=%s", msg.kind, msg.reason)
        return {"ok": True, "state": self._sm.state}
