"""The protocol state machine over ProtocolState."""

from __future__ import annotations

import logging

from cop_worker.mcp.protocol import _LEGAL, _TERMINAL, ProtocolState

logger = logging.getLogger(__name__)


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
