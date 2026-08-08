"""Tests for protocol adapter contract coverage."""

import inspect

from league_manager.protocol.base import ProtocolAdapter
from league_manager.protocol.reference_v3_adapter import ReferenceV3Adapter


def test_reference_v3_adapter_is_protocol_adapter():
    """ReferenceV3Adapter must be a subclass of ProtocolAdapter."""
    assert issubclass(ReferenceV3Adapter, ProtocolAdapter)


def test_adapter_has_candidate_tool_names_method():
    """Adapter must expose candidate_tool_names() classmethod or method."""
    assert hasattr(ReferenceV3Adapter, "candidate_tool_names")


def test_base_adapter_is_abstract():
    """ProtocolAdapter must be abstract — cannot be instantiated directly."""
    assert inspect.isabstract(ProtocolAdapter)


def test_adapter_normalise_negotiate_returns_dict():
    """normalise_negotiate must return a dict from a raw payload."""
    adapter = ReferenceV3Adapter()
    result = adapter.normalise_negotiate({"message": {"terms": {}, "group_id": "grp1"}})
    assert isinstance(result, dict)
    assert "terms" in result


def test_adapter_serialise_response_is_identity_for_simple_dict():
    """serialise_response must return a dict from a domain response."""
    adapter = ReferenceV3Adapter()
    resp = {"ok": True, "state": "PLAYING"}
    out = adapter.serialise_response(resp)
    assert isinstance(out, dict)
    assert out["ok"] is True
