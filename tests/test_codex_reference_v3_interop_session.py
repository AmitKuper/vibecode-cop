from __future__ import annotations

import copy
import json

import pytest

from cop_worker.protocol.reference_v3 import (
    REFERENCE_V3_TOOLS,
    ReferenceV3EquivocationError,
    ReferenceV3Error,
    ReferenceV3Inbox,
    ReferenceV3Session,
    build_negotiation,
    build_turn,
    default_terms,
    derive_game_id,
    derive_game_uid,
    verify_negotiation,
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
