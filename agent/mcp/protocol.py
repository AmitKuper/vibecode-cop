"""Protocol state machine and phase management."""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ProtocolState(Enum):
    IDLE = "idle"
    HANDSHAKE = "handshake"
    PLAYING = "playing"
    AUDITING = "auditing"
    DONE = "done"
    ABORTED = "aborted"


class ProtocolPhase(Enum):
    COMMIT = "commit"
    ACK = "ack"
    REVEAL = "reveal"
    FINAL_AUDIT = "final_audit"
    ABORT = "abort"


# Legal phase transitions (from state, from phase → to_phase)
_LEGAL_TRANSITIONS = {
    ProtocolState.IDLE: {
        None: [ProtocolPhase.COMMIT],
    },
    ProtocolState.HANDSHAKE: {
        ProtocolPhase.COMMIT: [ProtocolPhase.ACK],
    },
    ProtocolState.PLAYING: {
        ProtocolPhase.ACK: [ProtocolPhase.COMMIT, ProtocolPhase.REVEAL],
        ProtocolPhase.COMMIT: [ProtocolPhase.ACK],
        ProtocolPhase.REVEAL: [ProtocolPhase.ACK],
    },
    ProtocolState.AUDITING: {
        ProtocolPhase.REVEAL: [ProtocolPhase.FINAL_AUDIT],
        ProtocolPhase.FINAL_AUDIT: [ProtocolPhase.ACK],
    },
    ProtocolState.DONE: {None: []},
    ProtocolState.ABORTED: {None: []},
}


class ProtocolStateMachine:
    """Manages protocol state and phase transitions."""

    def __init__(self):
        self.state = ProtocolState.IDLE
        self.current_phase: ProtocolPhase | None = None
        self.step = 0

    def can_transition(self, to_phase: ProtocolPhase) -> tuple[bool, str | None]:
        """Check if transition to to_phase is legal. Returns (is_legal, error_message)."""
        if self.state not in _LEGAL_TRANSITIONS:
            return False, f"Unknown state: {self.state}"
        legal_phases = _LEGAL_TRANSITIONS[self.state].get(self.current_phase)
        if legal_phases is None:
            return (False,
                    f"No transitions defined for state={self.state}, phase={self.current_phase}")
        if to_phase not in legal_phases:
            cur = self.current_phase.value if self.current_phase else "None"
            return False, f"Illegal transition: {self.state.value}/{cur} → {to_phase.value}"
        return True, None

    def transition(self, to_phase: ProtocolPhase) -> None:
        """Transition to new phase. Raises ValueError if illegal."""
        is_legal, error = self.can_transition(to_phase)
        if not is_legal:
            raise ValueError(error)
        old_phase = self.current_phase
        old_state = self.state
        self.current_phase = to_phase

        if to_phase == ProtocolPhase.COMMIT:
            if self.state == ProtocolState.IDLE:
                self.state = ProtocolState.HANDSHAKE
            elif self.state == ProtocolState.HANDSHAKE:
                self.state = ProtocolState.PLAYING
                self.step = 0
        elif to_phase == ProtocolPhase.ACK:
            if self.state == ProtocolState.HANDSHAKE:
                self.state = ProtocolState.PLAYING
                self.step = 0
        elif to_phase == ProtocolPhase.FINAL_AUDIT:
            self.state = ProtocolState.AUDITING
        elif to_phase == ProtocolPhase.ABORT:
            self.state = ProtocolState.ABORTED

        logger.info(
            f"Protocol transition: {old_state.value}/{old_phase.value if old_phase else 'None'} → "
            f"{self.state.value}/{to_phase.value}"
        )

    def advance_step(self) -> None:
        self.step += 1
        self.current_phase = None
        logger.debug(f"Advanced to step {self.step}")

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "phase": self.current_phase.value if self.current_phase else None,
            "step": self.step,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProtocolStateMachine":
        sm = cls()
        sm.state = ProtocolState(data["state"])
        sm.current_phase = (
            ProtocolPhase(data["phase"]) if data.get("phase") else None
        )
        sm.step = data.get("step", 0)
        return sm


# Re-export StepPhaseTracker for backwards compatibility
from agent.mcp.protocol_phases import StepPhaseTracker  # noqa: E402

__all__ = [
    "ProtocolState",
    "ProtocolPhase",
    "ProtocolStateMachine",
    "StepPhaseTracker",
]
