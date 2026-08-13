"""Cover AdapterResponseMixin extraction, validation, and helper branches."""

from __future__ import annotations

import pytest

from cop_worker.protocol.adapter import (
    DeterministicProtocolAdapter,
    ProtocolCompatibilityError,
)


def _adapter() -> DeterministicProtocolAdapter:
    return DeterministicProtocolAdapter.native()


def _commit_pm(adapter):
    return adapter._get_phase_mapping("commit")


def test_native_classmethod_builds_identity_adapter():
    adapter = _adapter()
    assert isinstance(adapter, DeterministicProtocolAdapter)


def test_adapt_response_extracts_canonical_fields():
    adapter = _adapter()
    raw = {"ok": True, "game_id": "g1", "phase": "commit"}
    result = adapter.adapt_response("commit", raw)
    assert result.extracted["game_id"] == "g1"
    assert result.phase == "commit"
    assert len(result.response_digest) == 16


def test_adapt_response_protected_field_ok_and_mismatch():
    adapter = _adapter()
    raw = {"ok": True, "game_id": "g1", "phase": "commit"}
    adapter.adapt_response("commit", raw, expected_protected={"game_id": "g1"})
    with pytest.raises(ProtocolCompatibilityError, match="mismatch"):
        adapter.adapt_response("commit", raw, expected_protected={"game_id": "other"})


def test_adapt_response_protected_field_missing():
    adapter = _adapter()
    raw = {"ok": True, "game_id": "g1", "phase": "commit"}
    with pytest.raises(ProtocolCompatibilityError, match="is missing"):
        adapter.adapt_response("commit", raw, expected_protected={"nonces": "x"})


def test_adapt_response_required_response_field_missing():
    adapter = _adapter()
    pm = _commit_pm(adapter)
    pm.required_response_fields = ["result_hash"]
    with pytest.raises(ProtocolCompatibilityError, match="Required response fields missing"):
        adapter.adapt_response("commit", {"ok": True, "game_id": "g", "phase": "commit"})


def test_get_phase_mapping_unknown_phase():
    adapter = _adapter()
    with pytest.raises(ProtocolCompatibilityError, match="No mapping for phase"):
        adapter._get_phase_mapping("no_such_phase")


def test_validate_request_reports_missing_required_fields():
    adapter = _adapter()
    pm = _commit_pm(adapter)
    with pytest.raises(ProtocolCompatibilityError, match="required fields missing"):
        adapter._validate_request({}, pm)


def test_deep_get_stops_on_non_dict():
    adapter = _adapter()
    assert adapter._deep_get({"a": 1}, "a.b") is None
    assert adapter._deep_get({"a": {"b": 5}}, "a.b") == 5


def test_check_schema_digest_detects_change():
    adapter = _adapter()
    assert adapter.check_schema_digest("native") is True
    assert adapter.check_schema_digest("changed") is False
