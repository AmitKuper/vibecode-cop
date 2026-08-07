"""Test that conflicting duplicate commits are rejected."""

import pytest

from cop_worker.commit_reveal import CommitRevealStateMachine, ProtocolViolationError


def test_same_identity_different_digest_rejected():
    """Different hash on same step must raise ProtocolViolationError."""
    sm = CommitRevealStateMachine(expected_step=1)
    sm.receive_commit(step=1, commitment_hash="a" * 64)
    with pytest.raises(ProtocolViolationError):
        sm.receive_commit(step=1, commitment_hash="b" * 64)
