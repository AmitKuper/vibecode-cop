"""Test that identical duplicate turns return cached response (idempotent)."""

from cop_worker.commit_reveal import CommitRevealStateMachine
from cop_worker.crypto import build_commitment


def test_identical_turn_returns_cached_response():
    """Same commitment hash on same step must not raise (idempotent)."""
    sm = CommitRevealStateMachine(expected_step=1)
    nonce = "n1"
    action = {"direction": "S"}
    commitment = build_commitment(nonce=nonce, action=action)
    result1 = sm.receive_commit(step=1, commitment_hash=commitment)
    result2 = sm.receive_commit(step=1, commitment_hash=commitment)
    assert result1 == result2
