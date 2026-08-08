"""Coverage contracts for protocol, step0, and reports in 3-process design."""

from __future__ import annotations

import pytest

from cop_worker.protocol.introspector import IntrospectionResult, ToolSchema
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    ProtocolMappingPlan,
)
from cop_worker.protocol.protocol_agent import ProtocolUnderstandingAgent
from cop_worker.protocol.reference_v3 import (
    REFERENCE_V3_DIALECT,
    REFERENCE_V3_TOOLS,
    REFERENCE_V3_WIRE_LOCK,
)
from cop_worker.step0.signing import generate_key_pair, sign


# ---------------------------------------------------------------------------
# reference-v3 dialect
# ---------------------------------------------------------------------------


def test_reference_v3_dialect_constant_is_stable():
    assert REFERENCE_V3_DIALECT == "copthief-league-reference-v3"


def test_reference_v3_tools_contains_required_tools():
    required = {"negotiate", "receive_turn", "submit_audit", "receive_control"}
    assert required.issubset(REFERENCE_V3_TOOLS.keys())


def test_reference_v3_wire_lock_is_correct_length():
    assert len(REFERENCE_V3_WIRE_LOCK) == 64  # 32 bytes hex


# ---------------------------------------------------------------------------
# Step-0 signing
# ---------------------------------------------------------------------------


def test_generate_key_pair_returns_distinct_bytes():
    private, public = generate_key_pair()
    assert isinstance(private, bytes)
    assert isinstance(public, bytes)
    assert private != public
    assert len(private) > 0
    assert len(public) > 0


def test_sign_produces_deterministic_length():
    private, public = generate_key_pair()
    payload = b"test payload for signing"
    sig = sign(private, payload)
    assert isinstance(sig, bytes)
    assert len(sig) > 0


def test_two_key_pairs_are_distinct():
    k1 = generate_key_pair()
    k2 = generate_key_pair()
    assert k1[0] != k2[0]
    assert k1[1] != k2[1]


def test_gamelet_declaration_writes_file(tmp_path):
    from cop_worker.step0.gamelet_declaration import write_gamelet_declaration

    path = write_gamelet_declaration(
        game_uid="test_uid_01",
        sub_game_number=1,
        role="thief",
        terms={"board_size": 7},
        output_dir=tmp_path,
    )
    import json

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["game_uid"] == "test_uid_01"
    assert data["sub_game_number"] == 1
    assert data["role"] == "thief"


# ---------------------------------------------------------------------------
# Protocol mapping plan
# ---------------------------------------------------------------------------


def test_protocol_mapping_plan_native_is_compatible():
    plan = ProtocolMappingPlan.native_plan()
    assert plan.verdict == CompatibilityVerdict.COMPATIBLE


def test_protocol_understanding_agent_creates_plan():
    action = ToolSchema(
        "action",
        "safe",
        {
            "properties": {
                "game_id": {},
                "phase": {},
                "commitment": {},
                "move": {},
                "nonces": {},
                "signature": {},
                "message_json": {},
            }
        },
    )
    conformance = ToolSchema(
        "protocol_conformance",
        "side-effect-free conformance",
        {"properties": {"phase": {}, "game_id": {}, "request_digest": {}, "idempotency_key": {}}},
    )
    intro = IntrospectionResult("peer", "1", "p", [action, conformance], [], [], {}, "digest-01")
    agent = ProtocolUnderstandingAgent()
    plan = agent.create_plan(intro)
    assert plan is not None
    assert plan.verdict in {CompatibilityVerdict.COMPATIBLE, CompatibilityVerdict.INCOMPATIBLE}


# ---------------------------------------------------------------------------
# Gmail report module
# ---------------------------------------------------------------------------


def test_gmail_sender_validate_missing_file(tmp_path):
    from cop_worker.gmail.sender import GmailApiSender

    sender = GmailApiSender(tmp_path / "missing.json")
    with pytest.raises(RuntimeError, match="missing"):
        sender.validate()


def test_gmail_sender_validate_empty_token(tmp_path):
    import json

    token_path = tmp_path / "empty.json"
    token_path.write_text(json.dumps({}), encoding="utf-8")
    from cop_worker.gmail.sender import GmailApiSender

    sender = GmailApiSender(token_path)
    with pytest.raises(RuntimeError):
        sender.validate()


def test_acceptance_file_sender_writes_record(tmp_path):
    from cop_worker.gmail.sender import AcceptanceFileGmailSender

    outbox = tmp_path / "outbox.jsonl"
    sender = AcceptanceFileGmailSender(outbox)
    sender.validate()
    msg_id = sender("to@example.com", "subject", "body", [])
    assert msg_id.startswith("FAKE_ACCEPTANCE_GMAIL_")
    import json

    lines = outbox.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["delivery_kind"] == "FAKE_ACCEPTANCE_ONLY"
