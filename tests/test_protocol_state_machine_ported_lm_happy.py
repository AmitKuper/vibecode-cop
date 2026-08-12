"""Adversarial protocol state machine tests — happy path.

Verifies the 16-state machine rejects illegal orderings, duplicates,
and race conditions while accepting the valid happy path.
"""

from __future__ import annotations

from cop_worker.mcp.protocol import ProtocolState
from tests.helpers_protocol_sm import advance_to, fresh_sm

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_session_setup(self):
        sm = fresh_sm()
        advance_to(sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY)
        assert sm.state == ProtocolState.READY

    def test_one_step_cop_commits_first(self):
        """Cop sends commit before receiving thief commit."""
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,  # cop sends commit
            ProtocolState.BOTH_COMMITTED,  # thief commit received
            ProtocolState.REVEAL_SENT,  # cop sends reveal
            ProtocolState.STEP_VERIFIED,  # thief reveal received
        )
        assert sm.state == ProtocolState.STEP_VERIFIED

    def test_one_step_thief_commits_first(self):
        """Thief commit arrives before cop has sent its own."""
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_RECEIVED,  # thief commit arrives first
            ProtocolState.BOTH_COMMITTED,  # cop then sends its commit
            ProtocolState.REVEAL_RECEIVED,  # thief reveal arrives first
            ProtocolState.STEP_VERIFIED,  # cop sends reveal
        )
        assert sm.state == ProtocolState.STEP_VERIFIED

    def test_multi_step_loop(self):
        sm = fresh_sm()
        advance_to(sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY)
        for _ in range(3):
            advance_to(
                sm,
                ProtocolState.COMPUTING_MOVE,
                ProtocolState.COMMIT_SENT,
                ProtocolState.BOTH_COMMITTED,
                ProtocolState.REVEAL_SENT,
                ProtocolState.STEP_VERIFIED,
            )
            sm.advance_step()
        assert sm.step == 3

    def test_full_audit_flow(self):
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
        assert sm.state == ProtocolState.DONE
