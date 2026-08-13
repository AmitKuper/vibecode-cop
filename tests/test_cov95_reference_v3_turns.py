"""Cover validation, inbox reorder, and audit-verification branches in turns.py."""

from __future__ import annotations

import pytest

from cop_worker.protocol.reference_v3.constants import (
    ReferenceV3EquivocationError,
    ReferenceV3Error,
)
from cop_worker.protocol.reference_v3.turns import (
    ReferenceV3Inbox,
    build_turn,
    validate_turn,
    verify_audit,
)


def _valid_turn(**overrides) -> dict:
    turn = {
        "step": 1,
        "sender": "police",
        "commit": "a" * 64,
        "hint": "ok",
        "smell_grid": {"0,0": 0.5},
    }
    turn.update(overrides)
    return turn


def test_validate_turn_field_and_value_errors():
    with pytest.raises(ReferenceV3Error, match="missing fields"):
        validate_turn({})
    with pytest.raises(ReferenceV3Error, match="police or thief"):
        validate_turn(_valid_turn(sender="robber"))
    with pytest.raises(ReferenceV3Error, match="positive integer"):
        validate_turn(_valid_turn(step=0))
    with pytest.raises(ReferenceV3Error, match="SHA-256 hex digest"):
        validate_turn(_valid_turn(commit="short"))
    with pytest.raises(ReferenceV3Error, match="hexadecimal"):
        validate_turn(_valid_turn(commit="z" * 64))
    with pytest.raises(ReferenceV3Error, match="only police"):
        validate_turn(_valid_turn(sender="thief", barrier_placed=[1, 2]))
    with pytest.raises(ReferenceV3Error, match="word cap"):
        validate_turn(_valid_turn(hint=" ".join(str(i) for i in range(20))))
    with pytest.raises(ReferenceV3Error, match="smell_grid must map"):
        validate_turn(_valid_turn(smell_grid={"0,0": "loud"}))


def _record(step: int, nonce: str, move: str):
    payload = {
        "step": step,
        "role": "police",
        "state": "grid=7x7",
        "position": [3, 4],
        "move": move,
        "intent": "truth",
        "hint": "x",
    }
    turn, record = build_turn(
        record_payload=payload,
        nonce=nonce,
        sender="police",
        hint="x",
        smell_grid={"3,4": 0.1},
    )
    return turn, record


def test_inbox_buffers_and_flushes_in_order():
    inbox = ReferenceV3Inbox()
    turn3, _ = _record(3, "11" * 16, "MOVE:N")
    assert inbox.offer(turn3) == []  # future step is buffered
    turn1, _ = _record(1, "22" * 16, "MOVE:S")
    turn2, _ = _record(2, "33" * 16, "MOVE:E")
    ready = inbox.offer(turn1)
    assert [m["step"] for m in ready] == [1]
    ready = inbox.offer(turn2)  # flush 2 then buffered 3
    assert [m["step"] for m in ready] == [2, 3]


def test_inbox_rejects_equivocation_and_window():
    inbox = ReferenceV3Inbox()
    turn1a, _ = _record(1, "11" * 16, "MOVE:N")
    inbox.offer(turn1a)
    turn1b, _ = _record(1, "22" * 16, "MOVE:S")  # same step, different commit
    with pytest.raises(ReferenceV3EquivocationError, match="already-played"):
        inbox.offer(turn1b)

    inbox2 = ReferenceV3Inbox()
    far, _ = _record(99, "44" * 16, "MOVE:N")
    with pytest.raises(ReferenceV3Error, match="reorder window"):
        inbox2.offer(far)


def test_inbox_rejects_buffered_equivocation():
    inbox = ReferenceV3Inbox()
    t3a, _ = _record(3, "11" * 16, "MOVE:N")
    t3b, _ = _record(3, "22" * 16, "MOVE:S")
    inbox.offer(t3a)  # buffered
    with pytest.raises(ReferenceV3EquivocationError, match="buffered commit"):
        inbox.offer(t3b)


def test_verify_audit_error_paths():
    ok, errors = verify_audit({}, {})
    assert not ok and "no records" in errors[0]

    ok, errors = verify_audit({"records": [123]}, {})
    assert not ok and "not an object" in errors[0]

    ok, errors = verify_audit({"records": [{"payload": {}}]}, {})
    assert not ok and "lacks payload/nonce/commit" in errors[0]


def test_verify_audit_detects_double_commitment():
    _, r1 = _record(1, "11" * 16, "MOVE:N")
    _, r2 = _record(1, "22" * 16, "MOVE:S")
    ok, errors = verify_audit({"records": [r1, r2]}, {})
    assert not ok
    assert any("two commitments" in e for e in errors)
