"""Branch tests for cop_worker.mcp.messages validators and message parsing."""

from __future__ import annotations

import pytest

from cop_worker.mcp.messages import (
    ActionMessage,
    StartGameMessage,
    validate_action_message,
    validate_start_game_message,
)

_SHA = "a" * 64


def _start(**overrides) -> StartGameMessage:
    base = {
        "game_id": "G1",
        "roles": {"cop": "us", "police": "them"},
        "config_sha256": _SHA,
        "protocol_version": "1.0",
        "endpoint": "http://localhost:5000/mcp",
        "timestamp": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return StartGameMessage(**base)


def _action(**overrides) -> ActionMessage:
    base = {
        "game_id": "G1",
        "step": 1,
        "role": "cop",
        "config_sha256": _SHA,
        "timestamp": "2026-01-01T00:00:00Z",
        "phase": "commit",
        "h_commit": "b" * 64,
    }
    base.update(overrides)
    return ActionMessage(**base)


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({}, None),
        ({"game_id": ""}, "game_id"),
        ({"roles": {"cop": "x"}}, "roles"),
        ({"roles": {}}, "roles"),
        ({"config_sha256": "short"}, "config_sha256"),
        ({"protocol_version": "2.0"}, "protocol_version"),
        ({"endpoint": "ftp://x"}, "endpoint"),
        ({"timestamp": ""}, "timestamp"),
    ],
)
def test_validate_start_game(overrides, fragment):
    ok, err = validate_start_game_message(_start(**overrides))
    if fragment is None:
        assert ok and err is None
    else:
        assert not ok and fragment in err


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({}, None),
        ({"game_id": ""}, "game_id"),
        ({"step": -1}, "step"),
        ({"role": "thief"}, "role"),
        ({"config_sha256": "zz"}, "config_sha256"),
        ({"timestamp": ""}, "timestamp"),
        ({"phase": "warp"}, "phase"),
        ({"h_commit": "tooshort"}, "h_commit"),
        ({"h_commit": None}, None),
        ({"phase": "ack", "h_commit_ack": None}, "h_commit_ack"),
        ({"phase": "ack", "h_commit_ack": "c" * 64}, None),
        ({"phase": "reveal", "move": "DIAGONAL"}, "move"),
        ({"phase": "reveal", "move": "PLACE_N"}, None),
        ({"phase": "reveal", "move": "N", "intent": "sarcasm"}, "intent"),
        ({"phase": "reveal", "move": "N", "hint": "w " * 16}, "15 words"),
        ({"phase": "reveal", "move": "N", "state_hash": "xy"}, "state_hash"),
        ({"phase": "reveal", "move": "N", "hint": "going north", "intent": "truth"}, None),
        ({"phase": "final_audit", "nonces": "notadict"}, "nonces"),
        ({"phase": "final_audit", "nonces": {"1": "n"}}, None),
        ({"phase": "final_audit", "nonces": None}, None),
        ({"phase": "audit_summary"}, "signed_audit_summary"),
        ({"phase": "audit_summary", "signed_audit_summary": {"sig": "s"}}, None),
        ({"phase": "abort"}, "reason"),
        ({"phase": "abort", "reason": "peer timeout"}, None),
        ({"phase": "game_end"}, "reason"),
        ({"phase": "game_end", "reason": "capture"}, None),
        ({"phase": "result_agreement"}, None),
    ],
)
def test_validate_action(overrides, fragment):
    ok, err = validate_action_message(_action(**overrides))
    if fragment is None:
        assert ok and err is None
    else:
        assert not ok and fragment in err


def test_start_game_json_roundtrip_ignores_unknown_fields():
    msg = _start(peer_url="http://peer", signed_declaration={"d": 1})
    payload = dict(msg.to_dict())
    payload["unknown_future_field"] = 42
    import json

    parsed = StartGameMessage.from_json(json.dumps(payload))
    assert parsed.to_dict() == msg.to_dict()
    with pytest.raises(ValueError, match="Invalid StartGameMessage"):
        StartGameMessage.from_json("not json")


def test_action_json_roundtrip_and_optional_fields():
    msg = _action(
        phase="reveal",
        move="N",
        hint="north now",
        intent="truth",
        state_hash="d" * 64,
        nonces={"0": "n"},
        game_log=[{"e": 1}],
        reason="r",
        board_state={"cop": [0, 0]},
        signed_audit_summary={"a": 1},
        signed_result_agreement={"b": 2},
        signed_audit_summaries=[{"c": 3}],
        h_commit_ack="e" * 64,
    )
    parsed = ActionMessage.from_json(__import__("json").dumps(msg.to_dict()))
    assert parsed.to_dict() == msg.to_dict()
    assert "signed_audit_summaries" in msg.to_dict()
    with pytest.raises(ValueError, match="Invalid ActionMessage"):
        ActionMessage.from_json("{]")
