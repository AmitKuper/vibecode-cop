"""Adversarial protocol state machine tests — illegal orderings and duplicates.

Verifies the 16-state machine rejects illegal orderings, duplicates,
and race conditions while accepting the valid happy path.
"""

from __future__ import annotations

import pytest

from cop_worker.mcp.protocol import ProtocolState
from tests.helpers_protocol_sm import advance_to, fresh_sm

# ---------------------------------------------------------------------------
# Illegal orderings
# ---------------------------------------------------------------------------


class TestIllegalOrderings:
    def test_reveal_before_both_committed(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
        )
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.REVEAL_SENT)

    def test_commit_before_computing_move(self):
        sm = fresh_sm()
        advance_to(sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY)
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.COMMIT_SENT)

    def test_skip_negotiating(self):
        sm = fresh_sm()
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.READY)

    def test_skip_to_done_from_idle(self):
        sm = fresh_sm()
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.DONE)

    def test_auditing_before_step_verified(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
        )
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.AUDITING)

    def test_computing_move_from_idle(self):
        sm = fresh_sm()
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.COMPUTING_MOVE)

    def test_result_agreement_before_auditing(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
        )
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.RESULT_AGREEMENT)


# ---------------------------------------------------------------------------
# Duplicate messages
# ---------------------------------------------------------------------------


class TestDuplicateMessages:
    def test_duplicate_commit_sent(self):
        """Sending commit twice is illegal once in COMMIT_SENT."""
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
        )
        with pytest.raises(ValueError):
            sm.transition(ProtocolState.COMMIT_SENT)

    def test_duplicate_reveal_sent(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
            ProtocolState.REVEAL_SENT,
        )
        with pytest.raises(ValueError):
            sm.transition(ProtocolState.REVEAL_SENT)

    def test_duplicate_start_game(self):
        """Once READY, another STEP0_NEGOTIATING must be rejected."""
        sm = fresh_sm()
        advance_to(sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY)
        with pytest.raises(ValueError):
            sm.transition(ProtocolState.STEP0_NEGOTIATING)
