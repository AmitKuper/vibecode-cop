"""Protocol state machine — 16-state per-step lifecycle."""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ProtocolState(Enum):
    IDLE = "idle"
    STEP0_NEGOTIATING = "step0_negotiating"
    READY = "ready"
    COMPUTING_MOVE = "computing_move"
    COMMIT_SENT = "commit_sent"
    COMMIT_RECEIVED = "commit_received"
    BOTH_COMMITTED = "both_committed"
    REVEAL_SENT = "reveal_sent"
    REVEAL_RECEIVED = "reveal_received"
    STEP_VERIFIED = "step_verified"
    AUDITING = "auditing"
    RESULT_AGREEMENT = "result_agreement"
    REPORTING = "reporting"
    DONE = "done"
    TECHNICAL_LOSS = "technical_loss"
    ABORTED = "aborted"


# Terminal states that reject all further transitions.
_TERMINAL = frozenset({ProtocolState.DONE, ProtocolState.TECHNICAL_LOSS, ProtocolState.ABORTED})

# Legal (from_state, to_state) pairs.
# ABORTED and TECHNICAL_LOSS are reachable from any non-terminal state (handled separately).
_LEGAL: frozenset[tuple[ProtocolState, ProtocolState]] = frozenset(
    {
        # Session setup
        (ProtocolState.IDLE, ProtocolState.STEP0_NEGOTIATING),
        (ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY),
        # Step start
        (ProtocolState.READY, ProtocolState.COMPUTING_MOVE),
        (ProtocolState.STEP_VERIFIED, ProtocolState.COMPUTING_MOVE),  # next step
        # Commit phase — either side may commit first
        (ProtocolState.COMPUTING_MOVE, ProtocolState.COMMIT_SENT),
        (ProtocolState.COMPUTING_MOVE, ProtocolState.COMMIT_RECEIVED),
        (ProtocolState.COMMIT_SENT, ProtocolState.BOTH_COMMITTED),
        (ProtocolState.COMMIT_RECEIVED, ProtocolState.BOTH_COMMITTED),
        # Reveal phase — either side may reveal first
        (ProtocolState.BOTH_COMMITTED, ProtocolState.REVEAL_SENT),
        (ProtocolState.BOTH_COMMITTED, ProtocolState.REVEAL_RECEIVED),
        (ProtocolState.REVEAL_SENT, ProtocolState.STEP_VERIFIED),
        (ProtocolState.REVEAL_RECEIVED, ProtocolState.STEP_VERIFIED),
        # Final audit flow
        (ProtocolState.STEP_VERIFIED, ProtocolState.AUDITING),
        (ProtocolState.AUDITING, ProtocolState.RESULT_AGREEMENT),
        (ProtocolState.RESULT_AGREEMENT, ProtocolState.REPORTING),
        (ProtocolState.REPORTING, ProtocolState.DONE),
    }
)


class ProtocolStateMachine:
    """Per-session protocol state machine.

    Guards that actions arrive in the correct order within one gamelet.
    Thread-safe when callers hold the accompanying session lock.
    """

    def __init__(self) -> None:
        self.state = ProtocolState.IDLE
        self.step = 0

    # ------------------------------------------------------------------
    # Transition API
    # ------------------------------------------------------------------

    def can_transition(self, to_state: ProtocolState) -> tuple[bool, str | None]:
        """Return (ok, error) without mutating state."""
        if self.state in _TERMINAL:
            return False, f"State {self.state.value} is terminal — no further transitions"
        if to_state in (ProtocolState.ABORTED, ProtocolState.TECHNICAL_LOSS):
            return True, None
        if (self.state, to_state) not in _LEGAL:
            return (
                False,
                f"Illegal transition: {self.state.value} → {to_state.value}",
            )
        return True, None

    def transition(self, to_state: ProtocolState) -> None:
        """Mutate state. Raises ValueError if transition is illegal."""
        ok, err = self.can_transition(to_state)
        if not ok:
            raise ValueError(err)
        prev = self.state
        self.state = to_state
        logger.info("Protocol: %s → %s (step=%d)", prev.value, to_state.value, self.step)

    def advance_step(self) -> None:
        """Increment step counter after STEP_VERIFIED → COMPUTING_MOVE."""
        self.step += 1
        logger.debug("Step advanced to %d", self.step)

    # ------------------------------------------------------------------
    # Convenience guards for server_handlers
    # ------------------------------------------------------------------

    def guard_commit_received(self) -> tuple[bool, str | None]:
        """Check whether receiving a peer commit is legal now."""
        if self.state == ProtocolState.COMPUTING_MOVE:
            return True, None
        if self.state == ProtocolState.COMMIT_SENT:
            return True, None
        return False, f"Received commit in unexpected state {self.state.value}"

    def guard_reveal_received(self) -> tuple[bool, str | None]:
        """Check whether receiving a peer reveal is legal now."""
        if self.state == ProtocolState.BOTH_COMMITTED:
            return True, None
        if self.state == ProtocolState.REVEAL_SENT:
            return True, None
        return False, f"Received reveal in unexpected state {self.state.value}"

    def guard_final_audit_received(self) -> tuple[bool, str | None]:
        if self.state == ProtocolState.AUDITING:
            return True, None
        return False, f"Received final_audit in unexpected state {self.state.value}"

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {"state": self.state.value, "step": self.step}

    @classmethod
    def from_dict(cls, data: dict) -> ProtocolStateMachine:
        sm = cls()
        sm.state = ProtocolState(data["state"])
        sm.step = data.get("step", 0)
        return sm


# ---------------------------------------------------------------------------
# Backwards-compatibility shims — old callers used ProtocolPhase and
# StepPhaseTracker.  Keep them importable so existing tests don't break.
# ---------------------------------------------------------------------------


class ProtocolPhase(Enum):
    COMMIT = "commit"
    ACK = "ack"
    REVEAL = "reveal"
    FINAL_AUDIT = "final_audit"
    ABORT = "abort"


from cop_worker.mcp.protocol_phases import StepPhaseTracker  # noqa: E402

__all__ = [
    "ProtocolState",
    "ProtocolPhase",
    "ProtocolStateMachine",
    "StepPhaseTracker",
]
