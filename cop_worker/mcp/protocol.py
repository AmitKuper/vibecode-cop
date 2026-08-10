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


from cop_worker.mcp.protocol_sm import (  # noqa: E402  (re-export)
    ProtocolStateMachine,
)
