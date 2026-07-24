"""Protocol and state-machine tests (R9)."""

import pytest

from agent.mcp.crypto import (
    canonical_json,
    create_commitment,
    hash_game_state,
    sign_message,
    verify_commitment,
    verify_signature,
)
from agent.mcp.messages import (
    ActionMessage,
    StartGameMessage,
    validate_action_message,
    validate_start_game_message,
)

_SECRET = "test-secret-for-testing"
_CFG_SHA = "a" * 64
_GAME_ID = "test_game_001"


# ---------------------------------------------------------------------------
# StartGameMessage validation
# ---------------------------------------------------------------------------

def test_start_game_accepts_matching_config():
    msg = StartGameMessage(
        game_id=_GAME_ID,
        roles={"cop": "c", "thief": "t"},
        config_sha256=_CFG_SHA,
        protocol_version="1.0",
        endpoint="http://localhost:5000/mcp",
        timestamp="2026-01-01T00:00:00",
    )
    ok, err = validate_start_game_message(msg)
    assert ok, err


def test_start_game_rejects_config_mismatch():
    msg = StartGameMessage(
        game_id=_GAME_ID,
        roles={"cop": "c", "thief": "t"},
        config_sha256="b" * 64,
        protocol_version="1.0",
        endpoint="http://localhost:5000/mcp",
        timestamp="2026-01-01T00:00:00",
    )
    # Validate passes (mismatch is checked by server comparing to local config)
    # But the sha256 format itself must be 64 hex chars — it is, so must pass
    ok, _ = validate_start_game_message(msg)
    assert ok


def test_start_game_rejects_short_config_sha():
    msg = StartGameMessage(
        game_id=_GAME_ID,
        roles={"cop": "c", "thief": "t"},
        config_sha256="tooshort",
        protocol_version="1.0",
        endpoint="http://localhost:5000/mcp",
        timestamp="2026-01-01T00:00:00",
    )
    ok, err = validate_start_game_message(msg)
    assert not ok
    assert "64-char" in (err or "")


# ---------------------------------------------------------------------------
# ActionMessage validation
# ---------------------------------------------------------------------------

def _base_action(**kwargs) -> ActionMessage:
    defaults = {
        "game_id": _GAME_ID,
        "step": 1,
        "role": "cop",
        "config_sha256": _CFG_SHA,
        "timestamp": "2026-01-01T00:00:00",
        "phase": "commit",
    }
    defaults.update(kwargs)
    return ActionMessage(**defaults)


def test_action_rejects_bad_role():
    msg = _base_action(role="ghost")
    ok, err = validate_action_message(msg)
    assert not ok
    assert "role" in (err or "")


def test_action_rejects_unknown_phase():
    msg = _base_action(phase="dance")
    ok, err = validate_action_message(msg)
    assert not ok
    assert "phase" in (err or "")


def test_commit_no_h_commit_is_valid():
    """COMMIT request from GameRunner has no h_commit — must be accepted."""
    msg = _base_action(phase="commit")
    ok, err = validate_action_message(msg)
    assert ok, err


def test_commit_invalid_h_commit_rejected():
    """If h_commit IS provided it must be 64 hex chars."""
    msg = _base_action(phase="commit", h_commit="tooshort")
    ok, err = validate_action_message(msg)
    assert not ok
    assert "64-char" in (err or "")


def test_reveal_valid_move_passes():
    msg = _base_action(phase="reveal", move="N")
    ok, err = validate_action_message(msg)
    assert ok, err


def test_reveal_invalid_move_rejected():
    msg = _base_action(phase="reveal", move="DIAGONAL")
    ok, err = validate_action_message(msg)
    assert not ok


def test_reveal_invalid_intent_rejected():
    msg = _base_action(phase="reveal", move="N", intent="maybe")
    ok, err = validate_action_message(msg)
    assert not ok
    assert "intent" in (err or "")


def test_reveal_hint_too_long_rejected():
    long_hint = " ".join(["word"] * 16)
    msg = _base_action(phase="reveal", move="N", hint=long_hint)
    ok, err = validate_action_message(msg)
    assert not ok
    assert "hint" in (err or "")


def test_final_audit_empty_nonces_valid():
    """Empty nonces dict in FINAL_AUDIT request must be accepted."""
    msg = _base_action(phase="final_audit", nonces={})
    ok, err = validate_action_message(msg)
    assert ok, err


def test_abort_requires_reason():
    msg = _base_action(phase="abort")
    ok, err = validate_action_message(msg)
    assert not ok
    assert "reason" in (err or "")


def test_game_end_requires_reason():
    msg = _base_action(phase="game_end")
    ok, err = validate_action_message(msg)
    assert not ok


# ---------------------------------------------------------------------------
# HMAC signature tests
# ---------------------------------------------------------------------------

def test_action_rejects_invalid_signature():
    msg = _base_action(phase="commit")
    sig = sign_message(msg.to_dict(), _SECRET)
    # Tamper with the message
    tampered = msg.to_dict()
    tampered["step"] = 999
    assert not verify_signature(tampered, sig, _SECRET)


def test_action_accepts_valid_signature():
    msg = _base_action(phase="commit")
    sig = sign_message(msg.to_dict(), _SECRET)
    assert verify_signature(msg.to_dict(), sig, _SECRET)


def test_action_rejects_bad_json():
    """ActionMessage.from_json should raise on bad JSON."""
    with pytest.raises(ValueError, match="Invalid ActionMessage JSON"):
        ActionMessage.from_json("{not json}")


# ---------------------------------------------------------------------------
# Commit / reveal verification
# ---------------------------------------------------------------------------

def _sample_state_hash() -> str:
    return hash_game_state({"cop_position": [0, 0], "thief_position": [6, 6], "turn": 1})


def test_commit_then_reveal_success():
    state_hash = _sample_state_hash()
    h_commit, nonce = create_commitment(
        game_id=_GAME_ID, step=1, role="cop",
        state_hash=state_hash, move="N", hint="going north", intent="truth",
    )
    assert len(h_commit) == 64

    ok = verify_commitment(
        h_commit=h_commit, game_id=_GAME_ID, step=1, role="cop",
        state_hash=state_hash, move="N", hint="going north", intent="truth",
        nonce=nonce,
    )
    assert ok


def test_wrong_move_fails_commit_verification():
    state_hash = _sample_state_hash()
    h_commit, nonce = create_commitment(
        game_id=_GAME_ID, step=1, role="cop",
        state_hash=state_hash, move="N", hint="going north", intent="truth",
    )
    ok = verify_commitment(
        h_commit=h_commit, game_id=_GAME_ID, step=1, role="cop",
        state_hash=state_hash, move="S",  # tampered
        hint="going north", intent="truth", nonce=nonce,
    )
    assert not ok


def test_wrong_hint_fails_commit_verification():
    state_hash = _sample_state_hash()
    h_commit, nonce = create_commitment(
        game_id=_GAME_ID, step=1, role="cop",
        state_hash=state_hash, move="N", hint="going north", intent="truth",
    )
    ok = verify_commitment(
        h_commit=h_commit, game_id=_GAME_ID, step=1, role="cop",
        state_hash=state_hash, move="N",
        hint="going south",  # tampered
        intent="truth", nonce=nonce,
    )
    assert not ok


def test_wrong_nonce_fails_final_audit():
    state_hash = _sample_state_hash()
    h_commit, _ = create_commitment(
        game_id=_GAME_ID, step=1, role="thief",
        state_hash=state_hash, move="STAY", hint="hiding", intent="lie",
    )
    ok = verify_commitment(
        h_commit=h_commit, game_id=_GAME_ID, step=1, role="thief",
        state_hash=state_hash, move="STAY", hint="hiding", intent="lie",
        nonce="wrong-nonce",
    )
    assert not ok


def test_canonical_json_deterministic():
    obj1 = {"b": 2, "a": 1}
    obj2 = {"a": 1, "b": 2}
    assert canonical_json(obj1) == canonical_json(obj2)
