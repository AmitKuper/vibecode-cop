from __future__ import annotations

import copy
import json

import pytest

from cop_worker.protocol.introspector import IntrospectionResult, ToolSchema
from cop_worker.protocol.reference_v3 import (
    REFERENCE_V3_TOOLS,
    REFERENCE_V3_WIRE_LOCK,
    ReferenceV3EquivocationError,
    ReferenceV3Error,
    ReferenceV3Inbox,
    ReferenceV3Profile,
    ReferenceV3Session,
    assert_core_vectors,
    build_negotiation,
    build_turn,
    default_terms,
    derive_game_id,
    derive_game_uid,
    is_reference_v3_surface,
    reference_commit,
    verify_audit,
    verify_negotiation,
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


def _greetings() -> tuple[dict, dict]:
    terms = default_terms()
    ours = build_negotiation(
        terms=terms,
        nonce="11" * 16,
        group_id="sparring-ours",
        group_name="Ours",
        role="police",
        sub_game_number=1,
    )
    theirs = build_negotiation(
        terms=terms,
        nonce="22" * 16,
        group_id="sparring-theirs",
        group_name="Theirs",
        role="thief",
        sub_game_number=1,
        opponent_group="sparring-ours",
    )
    return ours, theirs


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


def test_signed_pairing_and_uid_fail_closed() -> None:
    ours, theirs = _greetings()
    agreed = verify_negotiation(ours, theirs)
    assert agreed.game_id == derive_game_id("sparring-ours", "sparring-theirs")
    assert agreed.game_uid == derive_game_uid(default_terms(), "sparring-ours", "sparring-theirs")

    bad_signature = copy.deepcopy(theirs)
    bad_signature["signature"] = "0" * 64
    with pytest.raises(ReferenceV3Error, match="SPAR-N04"):
        verify_negotiation(ours, bad_signature)

    collision = copy.deepcopy(theirs)
    collision["role"] = "police"
    with pytest.raises(ReferenceV3Error, match="SPAR-N07"):
        verify_negotiation(ours, collision)

    drift = copy.deepcopy(theirs)
    drift["wire_shape_sha256"] = "f" * 64
    with pytest.raises(ReferenceV3Error, match="SPAR-N05"):
        verify_negotiation(ours, drift)


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


def test_at_least_once_dedupe_reorder_and_equivocation() -> None:
    inbox = ReferenceV3Inbox(window=2)

    def turn(step: int, commit: str) -> dict:
        return {
            "step": step,
            "sender": "police",
            "commit": commit,
            "hint": "",
            "smell_grid": {},
        }

    first, second = turn(1, "a" * 64), turn(2, "b" * 64)
    assert inbox.offer(second) == []
    assert inbox.offer(first) == [first, second]
    assert inbox.offer(first) == []
    with pytest.raises(ReferenceV3EquivocationError):
        inbox.offer(turn(1, "c" * 64))
    with pytest.raises(ReferenceV3Error, match="reorder window"):
        ReferenceV3Inbox(window=1).offer(turn(3, "d" * 64))


@pytest.mark.asyncio
async def test_deterministic_session_calls_exact_four_tools() -> None:
    calls: list[tuple[str, dict]] = []

    async def caller(name: str, params: dict) -> dict:
        calls.append((name, params))
        return {"ok": True}

    session = ReferenceV3Session(caller)
    ours, _ = _greetings()
    await session.send_negotiation(ours)
    turn, record = build_turn(
        record_payload={"step": 1, "move": "STAY", "position": [0, 0]},
        nonce="44" * 16,
        sender="police",
        hint="",
        smell_grid={},
    )
    await session.send_turn(turn, record)
    await session.send_audit("police", "timeout")
    await session.send_control(
        {"kind": "status", "sender": "police", "sub_game_number": 1, "payload": {}}
    )
    assert [name for name, _ in calls] == list(REFERENCE_V3_TOOLS)
    assert set(calls[0][1]) == {"message"}
    assert set(calls[2][1]) == {"payload"}
    assert session.per_turn_llm_calls == 0


def test_invalid_native_start_probe_preserves_protected_response_fields(tmp_path) -> None:
    from cop_worker.mcp.server_handlers import handle_start_game

    game_id = "PROBE_GAME_response_contract"
    response = handle_start_game(
        "police",
        "secret",
        "0" * 64,
        tmp_path,
        {},
        {},
        json.dumps({"game_id": game_id, "phase": "start_game"}),
        "a" * 64,
    )
    assert response["ok"] is False
    assert response["game_id"] == game_id
    assert response["phase"] == "start_game"
