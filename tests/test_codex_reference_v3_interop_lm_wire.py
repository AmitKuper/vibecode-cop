from __future__ import annotations

import copy

from league_manager.protocol.introspector import IntrospectionResult, ToolSchema
from league_manager.protocol.reference_v3 import (
    REFERENCE_V3_TOOLS,
    REFERENCE_V3_WIRE_LOCK,
    ReferenceV3Profile,
    assert_core_vectors,
    build_turn,
    is_reference_v3_surface,
    reference_commit,
    verify_audit,
)


def _intro(*, corrupt: str = "") -> IntrospectionResult:
    tools = []
    for name, argument in REFERENCE_V3_TOOLS.items():
        arg = "message" if name == corrupt else argument
        tools.append(
            ToolSchema(
                name=name,
                description=f"reference-v3 {name}",
                input_schema={
                    "type": "object",
                    "properties": {arg: {"type": "object"}},
                    "required": [arg],
                },
            )
        )
    return IntrospectionResult(
        server_name="copthief-sparring-peer",
        server_version="3",
        protocol_version="2025-06-18",
        tools=tools,
        resources=[],
        prompts=[],
        raw_capabilities={"tools": {}},
        schema_digest="abc123",
    )


def test_exact_surface_and_hashed_profile() -> None:
    intro = _intro()
    assert is_reference_v3_surface(intro)
    profile = ReferenceV3Profile.from_introspection(intro)
    assert profile.verify("abc123")
    assert profile.wire_lock_sha256 == REFERENCE_V3_WIRE_LOCK
    assert not profile.verify("changed")
    assert not is_reference_v3_surface(_intro(corrupt="submit_audit"))


def test_published_core_vectors_and_native_unicode() -> None:
    assert_core_vectors()
    payload = {
        "step": 1,
        "state": "grid=7x7;self=[4, 3];barriers=[]",
        "position": [4, 3],
        "move": "MOVE:S",
        "intent": "truth",
        "hint": "I keep to the main avenues.",
    }
    assert reference_commit(payload, "112233445566778899aabbccddeeff00") == (
        "aa6420e2d3a907d6c140856caecbb351b4d5ad98e381549c28268669af378dcc"
    )


def test_one_wire_turn_keeps_nonce_and_move_private_until_audit() -> None:
    private = {
        "step": 1,
        "role": "police",
        "sub_game": 1,
        "state": "grid=7x7;self=[3, 4];barriers=[]",
        "position": [3, 4],
        "move": "MOVE:E",
        "intent": "truth",
        "hint": "I moved west",
        "verdict": "moved",
    }
    turn, record = build_turn(
        record_payload=private,
        nonce="33" * 16,
        sender="police",
        hint=private["hint"],
        smell_grid={"3,4": 0.8},
    )
    assert "nonce" not in turn
    assert "move" not in turn
    assert turn["commit"] == record["commit"]
    ok, errors = verify_audit(
        {"sender": "police", "records": [record], "result_claim": "survival"},
        {1: turn["commit"]},
    )
    assert ok, errors

    tampered = copy.deepcopy(record)
    tampered["payload"]["move"] = "MOVE:W"
    ok, errors = verify_audit(
        {"sender": "police", "records": [tampered], "result_claim": "survival"},
        {1: turn["commit"]},
    )
    assert not ok
    assert "commitment mismatch" in errors[0]
