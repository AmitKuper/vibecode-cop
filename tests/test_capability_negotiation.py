"""Tests for capability negotiation (Phase 10C)."""
import pytest

from agent.mcp.capability_negotiation import (
    CapabilityDocument,
    CapabilityNegotiationError,
    validate_compatibility,
)


def _default() -> CapabilityDocument:
    return CapabilityDocument()


def test_compatible_caps_no_error():
    local = _default()
    remote = _default()
    validate_compatibility(local, remote)  # must not raise


def test_signature_mismatch_raises():
    local = _default()
    remote = _default()
    remote.signature_algorithms = ["HMAC-SHA256"]
    with pytest.raises(CapabilityNegotiationError, match="Signature algorithm mismatch"):
        validate_compatibility(local, remote)


def test_canonicalization_mismatch_raises():
    local = _default()
    remote = _default()
    remote.canonicalization = "cbor"
    with pytest.raises(CapabilityNegotiationError, match="Canonicalization mismatch"):
        validate_compatibility(local, remote)


def test_commitment_semantics_mismatch_raises():
    local = _default()
    remote = _default()
    remote.commitment_payload_semantics = "move_only"
    with pytest.raises(CapabilityNegotiationError, match="Commitment semantics mismatch"):
        validate_compatibility(local, remote)


def test_missing_required_phase_raises():
    local = _default()
    remote = _default()
    remote.supported_phases = ["reveal", "final_audit", "start_game"]  # missing "commit"
    with pytest.raises(CapabilityNegotiationError, match="missing required phases"):
        validate_compatibility(local, remote)


def test_capability_hash_deterministic():
    doc1 = _default()
    doc2 = _default()
    assert doc1.capability_hash() == doc2.capability_hash()


def test_capability_hash_changes_on_diff():
    doc1 = _default()
    doc2 = _default()
    doc2.mcp_transport = "StreamableHTTP"
    assert doc1.capability_hash() != doc2.capability_hash()
