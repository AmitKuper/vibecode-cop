"""Cover the turn/reveal/audit/control inbound handlers in GameletEventMixin."""

from __future__ import annotations

import hashlib
import json

import pytest

from cop_worker.commit_reveal import ProtocolViolationError
from cop_worker.gamelet import Gamelet
from cop_worker.state_machine import GameletState
from cop_worker.synthetic_belief import SyntheticBeliefProvider

VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
    "setting": "Haifa",
    "hint_max_words": 15,
    "axis_origin_corner": "top-left",
    "axis_start_index": 0,
    "thief_start": [3, 3],
    "cop_start": [0, 0],
}


def _gamelet(role: str = "police") -> Gamelet:
    return Gamelet(
        game_uid="test-uid-0001",
        sub_game_number=1,
        terms=VALID_TERMS,
        opponent_group="group-B",
        role=role,
        belief_provider=SyntheticBeliefProvider(),
    )


def _commitment(nonce: str, action: dict) -> str:
    return hashlib.sha256((nonce + json.dumps(action, sort_keys=True)).encode()).hexdigest()


def test_turn_before_playing_is_rejected():
    g = _gamelet()
    with pytest.raises(ProtocolViolationError, match="turn in state"):
        g.process_event("opponent_turn", {"kind": "commit", "step": 1})


def test_commit_absorbs_hint_and_returns_our_commit():
    g = _gamelet()
    g.start_playing()
    resp = g.process_event(
        "opponent_turn",
        {
            "kind": "commit",
            "step": 1,
            "commitment_hash": "abc123",
            "smell_grid": {"0,0": 0.5},
            "hint": "heading north",
        },
    )
    assert resp["ok"] and resp["response_payload"]["kind"] == "commit"
    assert resp["response_payload"]["step"] == 1
    assert g._last_hint == "heading north"
    assert g._opponent_smell == {"0,0": 0.5}


def test_reveal_verifies_matching_commitment():
    g = _gamelet()
    g.start_playing()
    nonce, action = "opp-nonce", {"type": "move", "direction": "NORTH"}
    h = _commitment(nonce, action)
    g.process_event("opponent_turn", {"kind": "commit", "step": 1, "commitment_hash": h})
    resp = g.process_event(
        "opponent_turn",
        {"kind": "reveal", "step": 1, "nonce": nonce, "action": action},
    )
    payload = resp["response_payload"]
    assert payload["kind"] == "reveal" and payload["opponent_verified"] is True


def test_reveal_without_stored_commitment_is_unverified():
    g = _gamelet()
    g.start_playing()
    resp = g.process_event(
        "opponent_turn",
        {"kind": "reveal", "step": 5, "nonce": "n", "action": {"a": 1}},
    )
    assert resp["response_payload"]["opponent_verified"] is False


def test_reveal_with_mismatched_nonce_is_unverified():
    g = _gamelet()
    g.start_playing()
    h = _commitment("real-nonce", {"type": "move", "direction": "SOUTH"})
    g.process_event("opponent_turn", {"kind": "commit", "step": 1, "commitment_hash": h})
    resp = g.process_event(
        "opponent_turn",
        {"kind": "reveal", "step": 1, "nonce": "wrong", "action": {"x": 0}},
    )
    assert resp["response_payload"]["opponent_verified"] is False


def test_ack_turn_returns_generic_ack():
    g = _gamelet()
    g.start_playing()
    resp = g.process_event("opponent_turn", {"kind": "ack", "step": 1})
    assert resp["response_payload"] == {"ack": True}


def test_audit_transitions_to_settled():
    g = _gamelet()
    g.start_playing()
    # Audit is only legal once gameplay has terminated and auditing has begun.
    g._sm.transition(GameletState.GAMEPLAY_TERMINAL)
    g._sm.transition(GameletState.AUDITING)
    resp = g.process_event(
        "opponent_audit",
        {
            "game_uid": "test-uid-0001",
            "sub_game_number": 1,
            "role": "thief",
            "steps": [],
            "terminal_condition": "capture",
            "final_step": 1,
            "log_hash": "deadbeef",
        },
    )
    assert resp["state"] == GameletState.SETTLED
    assert g._result is not None


def test_control_signal_is_acknowledged():
    g = _gamelet()
    g.start_playing()
    resp = g.process_event("control_signal", {"kind": "ping", "reason": "health"})
    assert resp["ok"] and resp["state"] == GameletState.PLAYING
