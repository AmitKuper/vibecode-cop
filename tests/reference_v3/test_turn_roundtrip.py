"""Test that a turn sent and received produces the correct response."""

import hashlib
import json

from cop_worker.commit_reveal import CommitRevealState, CommitRevealStateMachine


def _make_commitment(nonce: str, action: dict) -> str:
    """Build commitment using the same formula as CommitRevealStateMachine.verify_reveal."""
    canonical = nonce + json.dumps(action, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def test_turn_sent_and_received_produces_correct_response():
    """A valid commit + ack + reveal + verify must complete STEP_COMPLETE."""
    sm = CommitRevealStateMachine(expected_step=1)
    nonce = "abc123"
    action = {"direction": "N"}
    commitment = _make_commitment(nonce=nonce, action=action)
    # Opponent commits; we ack
    sm.receive_commit(step=1, commitment_hash=commitment)
    # We send our commit
    our_nonce = "xyz789"
    our_action = {"direction": "S"}
    our_commitment = _make_commitment(nonce=our_nonce, action=our_action)
    sm.send_our_commit(step=1, commitment_hash=our_commitment)
    # Opponent acks our commit
    sm.receive_ack(step=1)
    # Opponent reveals
    sm.receive_reveal(step=1, nonce=nonce, action=action)
    # Verify the reveal — transitions to STEP_COMPLETE
    sm.verify_reveal(stored_hash=commitment, nonce=nonce, action=action)
    assert sm.state == CommitRevealState.STEP_COMPLETE
