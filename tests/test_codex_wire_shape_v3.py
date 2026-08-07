"""Tests for reference-v3 wire shape normalisation."""

from league_manager.protocol.reference_v3_adapter import ReferenceV3Adapter


def make_adapter():
    """Return a fresh ReferenceV3Adapter."""
    return ReferenceV3Adapter()


def test_normalise_turn_returns_step_field():
    """normalise_turn must include 'step' field."""
    adapter = make_adapter()
    result = adapter.normalise_turn({"message": {"step": 5, "sender": "thief"}})
    assert result["step"] == 5


def test_normalise_turn_returns_sender_field():
    """normalise_turn must include 'sender' field."""
    adapter = make_adapter()
    result = adapter.normalise_turn({"message": {"step": 1, "sender": "cop"}})
    assert result["sender"] == "cop"


def test_normalise_audit_returns_result_claim():
    """normalise_audit must include 'result_claim' field."""
    adapter = make_adapter()
    raw = {"payload": {"result_claim": "survival", "records": [], "sender": "thief"}}
    result = adapter.normalise_audit(raw)
    assert result["result_claim"] == "survival"


def test_normalise_control_returns_type():
    """normalise_control must include 'type' field."""
    adapter = make_adapter()
    raw = {"message": {"type": "abort", "data": {}}}
    result = adapter.normalise_control(raw)
    assert result["type"] == "abort"


def test_normalise_negotiate_extracts_group_id():
    """normalise_negotiate must include 'group_id' field."""
    adapter = make_adapter()
    raw = {"message": {"group_id": "GRPTEST", "terms": {}, "role": "police"}}
    result = adapter.normalise_negotiate(raw)
    assert result["group_id"] == "GRPTEST"


def test_missing_message_key_uses_root():
    """normalise_turn without 'message' key must still return a dict."""
    adapter = make_adapter()
    result = adapter.normalise_turn({"step": 7, "sender": "cop"})
    assert isinstance(result, dict)
