"""Tests for commit-reveal protocol state machine."""

import pytest

from cop_worker.commit_reveal import CommitRevealStateMachine, ProtocolViolationError


def test_receive_commit_returns_ack():
    """receive_commit at the correct step must return an ack dict."""
    cr = CommitRevealStateMachine(expected_step=1)
    ack = cr.receive_commit(step=1, commitment_hash="a" * 64)
    assert ack["ack"] is True
    assert ack["step"] == 1


def test_wrong_step_raises():
    """receive_commit with wrong step must raise ProtocolViolationError."""
    cr = CommitRevealStateMachine(expected_step=1)
    with pytest.raises(ProtocolViolationError):
        cr.receive_commit(step=2, commitment_hash="a" * 64)


def test_duplicate_identical_commit_is_idempotent():
    """Same commit hash at same step must return cached ack (idempotent)."""
    cr = CommitRevealStateMachine(expected_step=1)
    hash1 = "b" * 64
    ack1 = cr.receive_commit(step=1, commitment_hash=hash1)
    ack2 = cr.receive_commit(step=1, commitment_hash=hash1)
    assert ack1 == ack2


def test_conflicting_commit_raises():
    """Two different hashes at same step must raise ProtocolViolationError."""
    cr = CommitRevealStateMachine(expected_step=1)
    cr.receive_commit(step=1, commitment_hash="a" * 64)
    with pytest.raises(ProtocolViolationError):
        cr.receive_commit(step=1, commitment_hash="b" * 64)


def test_reveal_before_commit_raises():
    """reveal before any commit must raise ProtocolViolationError."""
    cr = CommitRevealStateMachine(expected_step=1)
    with pytest.raises(ProtocolViolationError):
        cr.receive_reveal(step=1, nonce="nonce123", action={"dir": "N"})


def test_verify_reveal_passes_on_correct_nonce():
    """verify_reveal must return True when nonce+action hash matches commitment."""
    import hashlib
    import json

    nonce = "mysecret"
    action = {"dir": "N"}
    canonical = nonce + json.dumps(action, sort_keys=True)
    h = hashlib.sha256(canonical.encode()).hexdigest()
    cr = CommitRevealStateMachine(expected_step=1)
    assert cr.verify_reveal(stored_hash=h, nonce=nonce, action=action) is True
