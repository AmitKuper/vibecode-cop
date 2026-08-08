"""Tests for cop_worker.commit_reveal — protocol enforcement and state transitions."""

from __future__ import annotations

import hashlib
import json

import pytest

from cop_worker.commit_reveal import (
    CommitRevealState,
    CommitRevealStateMachine,
    ProtocolViolationError,
)


def _make_hash(nonce: str, action: dict) -> str:
    """Build a SHA256 commitment hash matching verify_reveal logic."""
    canonical = nonce + json.dumps(action, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def test_reveal_before_commit_rejected() -> None:
    """Receiving a reveal before any commit raises ProtocolViolationError."""
    cr = CommitRevealStateMachine(expected_step=1)
    assert cr.state == CommitRevealState.WAITING_COMMIT
    with pytest.raises(ProtocolViolationError, match="reveal before commit"):
        cr.receive_reveal(step=1, nonce="abc", action={"move": "N"})


def test_conflicting_commit_rejected() -> None:
    """Same step with a different hash after first commit raises ProtocolViolationError."""
    cr = CommitRevealStateMachine(expected_step=1)
    cr.receive_commit(step=1, commitment_hash="aaa")
    assert cr.state == CommitRevealState.COMMIT_LOCKED
    with pytest.raises(ProtocolViolationError, match="conflicting commit"):
        cr.receive_commit(step=1, commitment_hash="bbb")


def test_duplicate_identical_commit_returns_cached() -> None:
    """Same step with identical hash returns the same cached ack object."""
    cr = CommitRevealStateMachine(expected_step=1)
    ack1 = cr.receive_commit(step=1, commitment_hash="same_hash")
    ack2 = cr.receive_commit(step=1, commitment_hash="same_hash")
    assert ack1 is ack2


def test_wrong_step_rejected() -> None:
    """Commit with wrong step number raises ProtocolViolationError."""
    cr = CommitRevealStateMachine(expected_step=5)
    with pytest.raises(ProtocolViolationError, match="expected step 5"):
        cr.receive_commit(step=3, commitment_hash="abc")


def test_full_happy_path() -> None:
    """Full commit-reveal cycle reaches STEP_COMPLETE state."""
    nonce = "random-nonce-42"
    action = {"move": "N"}
    stored_hash = _make_hash(nonce, action)

    cr = CommitRevealStateMachine(expected_step=1)
    assert cr.state == CommitRevealState.WAITING_COMMIT

    # Opponent sends commit
    ack = cr.receive_commit(step=1, commitment_hash=stored_hash)
    assert cr.state == CommitRevealState.COMMIT_LOCKED
    assert ack == {"ack": True, "step": 1}

    # We send our commit
    our_hash = _make_hash("our-nonce", {"move": "S"})
    cr.send_our_commit(step=1, commitment_hash=our_hash)
    assert cr.state == CommitRevealState.WAITING_ACK

    # We receive ack from opponent
    cr.receive_ack(step=1)
    assert cr.state == CommitRevealState.WAITING_REVEAL

    # Opponent reveals nonce + action
    cr.receive_reveal(step=1, nonce=nonce, action=action)
    assert cr.state == CommitRevealState.VERIFYING_REVEAL

    # Verify the reveal
    result = cr.verify_reveal(stored_hash=stored_hash, nonce=nonce, action=action)
    assert result is True
    assert cr.state == CommitRevealState.STEP_COMPLETE


def test_verify_reveal_wrong_hash_raises() -> None:
    """verify_reveal raises ProtocolViolationError when hash does not match."""
    nonce = "nonce-xyz"
    action = {"move": "E"}
    correct_hash = _make_hash(nonce, action)

    cr = CommitRevealStateMachine(expected_step=1)
    cr.receive_commit(step=1, commitment_hash=correct_hash)
    cr.send_our_commit(step=1, commitment_hash="x" * 64)
    cr.receive_ack(step=1)
    cr.receive_reveal(step=1, nonce=nonce, action=action)

    with pytest.raises(ProtocolViolationError, match="reveal verification failed"):
        cr.verify_reveal(stored_hash="wrong" * 12 + "0000", nonce=nonce, action=action)


def test_receive_ack_in_wrong_state_raises() -> None:
    """receive_ack in WAITING_COMMIT state raises ProtocolViolationError."""
    cr = CommitRevealStateMachine(expected_step=1)
    with pytest.raises(ProtocolViolationError):
        cr.receive_ack(step=1)


def test_commit_returns_ack_dict() -> None:
    """receive_commit returns ack dict with correct step."""
    cr = CommitRevealStateMachine(expected_step=7)
    ack = cr.receive_commit(step=7, commitment_hash="deadbeef" * 8)
    assert ack["ack"] is True
    assert ack["step"] == 7
