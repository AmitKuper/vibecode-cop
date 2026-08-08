"""Tests for adaptive protocol detection and transport resilience."""

import pytest

from league_manager.protocol.reference_v3_adapter import ReferenceV3Adapter


def test_reference_v3_adapter_has_required_tool_names():
    """Adapter must expose the 4 required ref-v3 tool names."""
    names = ReferenceV3Adapter.candidate_tool_names()
    assert "negotiate" in names
    assert "receive_turn" in names
    assert "submit_audit" in names
    assert "receive_control" in names


def test_protocol_detection_error_is_raised_on_empty_tool_list():
    """detect_protocol must raise ProtocolDetectionError on empty tool list."""
    from unittest.mock import MagicMock, patch

    from league_manager.protocol.detection import ProtocolDetectionError, detect_protocol

    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"tools": []}'
    with (
        patch("urllib.request.urlopen", return_value=mock_resp),
        pytest.raises(ProtocolDetectionError),
    ):
        detect_protocol("http://fake-peer:9999")


def test_adapter_protocol_name():
    """Adapter must identify itself as reference-v3."""
    assert hasattr(ReferenceV3Adapter, "PROTOCOL_NAME")
    assert "reference" in ReferenceV3Adapter.PROTOCOL_NAME.lower()
