"""Adversarial protocol state machine tests — guard helpers and serialization.

Verifies the 16-state machine rejects illegal orderings, duplicates,
and race conditions while accepting the valid happy path.
"""

from __future__ import annotations

from cop_worker.mcp.protocol import ProtocolState, ProtocolStateMachine
from tests.helpers_protocol_sm import advance_to, fresh_sm

# ---------------------------------------------------------------------------
# Guard helpers
# ---------------------------------------------------------------------------


class TestGuardHelpers:
    def test_guard_commit_received_ok_in_computing_move(self):
        sm = fresh_sm()
        advance_to(
            sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY, ProtocolState.COMPUTING_MOVE
        )
        ok, err = sm.guard_commit_received()
        assert ok
        assert err is None

    def test_guard_commit_received_ok_after_commit_sent(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
        )
        ok, err = sm.guard_commit_received()
        assert ok

    def test_guard_commit_received_fail_in_both_committed(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
        )
        ok, _ = sm.guard_commit_received()
        assert not ok

    def test_guard_reveal_received_ok_in_both_committed(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
        )
        ok, err = sm.guard_reveal_received()
        assert ok
        assert err is None

    def test_guard_reveal_received_fail_in_computing_move(self):
        sm = fresh_sm()
        advance_to(
            sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY, ProtocolState.COMPUTING_MOVE
        )
        ok, _ = sm.guard_reveal_received()
        assert not ok

    def test_guard_final_audit_ok_in_auditing(self):
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
        )
        ok, _ = sm.guard_final_audit_received()
        assert ok


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_from_dict_round_trip(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
        )
        sm.advance_step()

        data = sm.to_dict()
        assert data["state"] == "commit_sent"
        assert data["step"] == 1

        sm2 = ProtocolStateMachine.from_dict(data)
        assert sm2.state == sm.state
        assert sm2.step == sm.step

    def test_all_states_serializable(self):
        for state in ProtocolState:
            sm = fresh_sm()
            sm.state = state
            data = sm.to_dict()
            sm2 = ProtocolStateMachine.from_dict(data)
            assert sm2.state == state
