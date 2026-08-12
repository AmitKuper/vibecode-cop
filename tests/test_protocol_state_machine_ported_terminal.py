"""Adversarial protocol state machine tests — terminal state enforcement.

Verifies the 16-state machine rejects illegal orderings, duplicates,
and race conditions while accepting the valid happy path.
"""

from __future__ import annotations

import pytest

from cop_worker.mcp.protocol import ProtocolState
from tests.helpers_protocol_sm import advance_to, fresh_sm

# ---------------------------------------------------------------------------
# Terminal state enforcement
# ---------------------------------------------------------------------------


class TestTerminalStates:
    def test_done_rejects_all(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
            ProtocolState.REVEAL_SENT,
            ProtocolState.STEP_VERIFIED,
            ProtocolState.AUDITING,
            ProtocolState.RESULT_AGREEMENT,
            ProtocolState.REPORTING,
            ProtocolState.DONE,
        )
        for target in ProtocolState:
            with pytest.raises(ValueError, match="terminal"):
                sm.transition(target)

    def test_aborted_rejects_all(self):
        sm = fresh_sm()
        advance_to(sm, ProtocolState.STEP0_NEGOTIATING)
        sm.transition(ProtocolState.ABORTED)
        for target in ProtocolState:
            with pytest.raises(ValueError, match="terminal"):
                sm.transition(target)

    def test_technical_loss_rejects_all(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
        )
        sm.transition(ProtocolState.TECHNICAL_LOSS)
        for target in ProtocolState:
            with pytest.raises(ValueError, match="terminal"):
                sm.transition(target)

    def test_abort_reachable_from_any_non_terminal(self):
        """ABORTED must be reachable from every non-terminal state."""
        non_terminal = [
            s
            for s in ProtocolState
            if s not in (ProtocolState.DONE, ProtocolState.TECHNICAL_LOSS, ProtocolState.ABORTED)
        ]
        for state in non_terminal:
            sm = fresh_sm()
            sm.state = state
            ok, err = sm.can_transition(ProtocolState.ABORTED)
            assert ok, f"ABORTED should be reachable from {state.value}: {err}"

    def test_technical_loss_reachable_from_any_non_terminal(self):
        non_terminal = [
            s
            for s in ProtocolState
            if s not in (ProtocolState.DONE, ProtocolState.TECHNICAL_LOSS, ProtocolState.ABORTED)
        ]
        for state in non_terminal:
            sm = fresh_sm()
            sm.state = state
            ok, err = sm.can_transition(ProtocolState.TECHNICAL_LOSS)
            assert ok, f"TECHNICAL_LOSS should be reachable from {state.value}: {err}"
