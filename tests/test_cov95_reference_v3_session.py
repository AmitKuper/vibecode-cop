"""Cover ReferenceV3Session send/receive methods and tool registration."""

from __future__ import annotations

import pytest

from cop_worker.protocol.reference_v3 import inbound_guard
from cop_worker.protocol.reference_v3.constants import (
    ReferenceV3EquivocationError,
    ReferenceV3Error,
)
from cop_worker.protocol.reference_v3.session import (
    ReferenceV3Session,
    register_reference_v3_tools,
)
from cop_worker.protocol.reference_v3.turns import build_turn


class _Caller:
    def __init__(self):
        self.calls = []

    async def __call__(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True, "tool": tool}


def _turn(step=1, nonce="11" * 16):
    payload = {"step": step, "role": "police", "move": "MOVE:N", "hint": "x"}
    return build_turn(
        record_payload=payload, nonce=nonce, sender="police", hint="x", smell_grid={"0,0": 0.1}
    )


async def test_send_helpers_and_local_record_dedup():
    caller = _Caller()
    session = ReferenceV3Session(caller)
    await session.send_negotiation({"hello": 1})
    turn, record = _turn()
    await session.send_turn(turn, record)
    assert len(session.local_records) == 1
    # Idempotent retry of the same bytes does not duplicate the local record.
    await session.send_turn(turn, record)
    assert len(session.local_records) == 1
    await session.send_audit("police", "survival")
    await session.send_control({"kind": "status"})
    assert [c[0] for c in caller.calls] == [
        "negotiate",
        "receive_turn",
        "receive_turn",
        "submit_audit",
        "receive_control",
    ]


async def test_send_turn_rejects_commit_mismatch_and_equivocation():
    session = ReferenceV3Session(_Caller())
    turn, record = _turn()
    bad = dict(record)
    bad["commit"] = "b" * 64
    with pytest.raises(ReferenceV3Error, match="different commits"):
        await session.send_turn(turn, bad)

    session2 = ReferenceV3Session(_Caller())
    turn1, record1 = _turn(step=1, nonce="11" * 16)
    await session2.send_turn(turn1, record1)
    turn2, record2 = _turn(step=1, nonce="22" * 16)  # same step, different commit
    with pytest.raises(ReferenceV3EquivocationError, match="different local commit"):
        await session2.send_turn(turn2, record2)


async def test_send_audit_rejects_bad_claim():
    session = ReferenceV3Session(_Caller())
    with pytest.raises(ReferenceV3Error, match="invalid reference-v3 result claim"):
        await session.send_audit("police", "banana")


def test_receive_turn_filters_unexpected_sender_and_stores():
    session = ReferenceV3Session(_Caller())
    session.expected_turn_sender = "thief"
    turn, _ = _turn()  # sender is police
    assert session.receive_turn(turn) == []  # discarded, wrong sender
    assert len(session.turn_messages) == 0

    session.expected_turn_sender = "police"
    ready = session.receive_turn(turn)
    assert [m["step"] for m in ready] == [1]
    assert len(session.turn_messages) == 1


def test_receive_negotiation_audit_control_queues():
    session = ReferenceV3Session(_Caller())
    session.receive_negotiation({"a": 1})
    session.receive_audit({"b": 2})
    session.receive_control({"c": 3})
    assert session.agreements[0] == {"a": 1}
    assert session.audits[0] == {"b": 2}
    assert session.controls[0] == {"c": 3}


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


def test_register_tools_dispatch_to_session():
    session = ReferenceV3Session(_Caller())
    mcp = _FakeMCP()
    register_reference_v3_tools(mcp, session)
    assert mcp.tools["negotiate"]({"m": 1}) == {"ok": True}
    turn, _ = _turn()
    assert mcp.tools["receive_turn"](turn) == {"ok": True}
    assert mcp.tools["submit_audit"]({"records": []}) == {"ok": True}
    assert mcp.tools["receive_control"]({"kind": "ping"}) == {"ok": True}
    assert session.agreements and session.audits and session.controls


def test_register_tools_refuse_when_flooded(monkeypatch):
    class _AlwaysRefuse:
        def __init__(self, *a, **kw):
            self.refused = 0

        def allow(self):
            self.refused += 1
            return False

    monkeypatch.setattr(inbound_guard, "InboundGuard", _AlwaysRefuse)
    session = ReferenceV3Session(_Caller())
    mcp = _FakeMCP()
    register_reference_v3_tools(mcp, session)
    for name in ("negotiate", "receive_turn", "submit_audit", "receive_control"):
        arg = {"payload": {}} if name == "submit_audit" else {"message": {}}
        result = mcp.tools[name](**arg)
        assert result == {"ok": False, "error": "rate_limited", "tool": name}
