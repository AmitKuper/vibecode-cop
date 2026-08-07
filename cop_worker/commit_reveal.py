"""Turn-level commit-reveal state machine for cop_worker."""

from __future__ import annotations

import hashlib
import json
import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class CommitRevealState(StrEnum):
    """States of the per-turn commit-reveal protocol."""

    WAITING_COMMIT = "WAITING_COMMIT"
    COMMIT_LOCKED = "COMMIT_LOCKED"
    WAITING_ACK = "WAITING_ACK"
    WAITING_REVEAL = "WAITING_REVEAL"
    VERIFYING_REVEAL = "VERIFYING_REVEAL"
    STEP_COMPLETE = "STEP_COMPLETE"


class ProtocolViolationError(Exception):
    """Raised when a protocol rule is violated."""


class CommitRevealStateMachine:
    """Manages the per-turn commit-reveal exchange.

    Enforces the commitment protocol: opponent commits first, then both reveal.
    Idempotent on duplicate identical commits (returns cached response).
    Rejects conflicting commits (same step, different hash).
    """

    def __init__(self, expected_step: int) -> None:
        """Initialise for a single turn at the given step number."""
        self._state = CommitRevealState.WAITING_COMMIT
        self._expected_step = expected_step
        self._opponent_hash: str | None = None
        self._our_hash: str | None = None
        self._cached_ack: dict | None = None

    @property
    def state(self) -> CommitRevealState:
        """Current commit-reveal state."""
        return self._state

    def receive_commit(self, step: int, commitment_hash: str) -> dict:
        """Process an incoming commitment from the opponent.

        Args:
            step: Turn step number from the opponent.
            commitment_hash: SHA256 hash of opponent's nonce+action.

        Returns:
            Acknowledgement dict to forward to opponent.

        Raises:
            ProtocolViolationError: On wrong step, conflicting commit, or bad state.
        """
        if step != self._expected_step:
            raise ProtocolViolationError(f"expected step {self._expected_step}, got {step}")
        if self._state == CommitRevealState.COMMIT_LOCKED:
            if commitment_hash == self._opponent_hash:
                # Idempotent: same step, same hash — return cached ack
                return self._cached_ack
            raise ProtocolViolationError(
                f"conflicting commit at step {step}: "
                f"stored={self._opponent_hash!r}, new={commitment_hash!r}"
            )
        if self._state != CommitRevealState.WAITING_COMMIT:
            raise ProtocolViolationError(f"receive_commit in state {self._state}")
        self._opponent_hash = commitment_hash
        self._state = CommitRevealState.COMMIT_LOCKED
        self._cached_ack = {"ack": True, "step": step}
        logger.debug("Received commit step=%d hash=%s", step, commitment_hash[:8])
        return self._cached_ack

    def send_our_commit(self, step: int, commitment_hash: str) -> None:
        """Record our outgoing commitment hash.

        Args:
            step: Turn step number.
            commitment_hash: SHA256 hash of our nonce+action.
        """
        self._our_hash = commitment_hash
        self._state = CommitRevealState.WAITING_ACK
        logger.debug("Sent commit step=%d hash=%s", step, commitment_hash[:8])

    def receive_ack(self, step: int) -> None:
        """Process opponent acknowledgement of our commit.

        Args:
            step: Turn step number.

        Raises:
            ProtocolViolationError: If not in WAITING_ACK state.
        """
        if self._state != CommitRevealState.WAITING_ACK:
            raise ProtocolViolationError(f"receive_ack in state {self._state}")
        self._state = CommitRevealState.WAITING_REVEAL
        logger.debug("Received ack step=%d", step)

    def receive_reveal(self, step: int, nonce: str, action: dict) -> None:
        """Process opponent's reveal of nonce and action.

        Args:
            step: Turn step number.
            nonce: The nonce the opponent is revealing.
            action: The action the opponent is revealing.

        Raises:
            ProtocolViolationError: If reveal arrives before commit or in wrong state.
        """
        if self._state == CommitRevealState.WAITING_COMMIT:
            raise ProtocolViolationError("reveal before commit")
        if self._state != CommitRevealState.WAITING_REVEAL:
            raise ProtocolViolationError(f"receive_reveal in state {self._state}")
        self._state = CommitRevealState.VERIFYING_REVEAL
        logger.debug("Received reveal step=%d action=%s", step, action)

    def verify_reveal(self, stored_hash: str, nonce: str, action: dict) -> bool:
        """Verify the opponent's revealed nonce matches the stored commitment.

        Args:
            stored_hash: The commitment hash received earlier.
            nonce: The nonce the opponent just revealed.
            action: The action the opponent just revealed.

        Returns:
            True if verification passes.

        Raises:
            ProtocolViolationError: If computed hash does not match stored hash.
        """
        canonical = nonce + json.dumps(action, sort_keys=True)
        computed = hashlib.sha256(canonical.encode()).hexdigest()
        if computed != stored_hash:
            raise ProtocolViolationError(
                f"reveal verification failed: computed={computed[:8]}, stored={stored_hash[:8]}"
            )
        self._state = CommitRevealState.STEP_COMPLETE
        return True
