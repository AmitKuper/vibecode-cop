"""Tests for report plugin base contracts."""

from pathlib import Path

import pytest

from agent.reports.base import ReportContext, ReportResult


def test_report_context_frozen():
    """ReportContext should be immutable."""
    context = ReportContext(
        game_id="test_001",
        role="cop",
        group_id="group_a",
        opponent_group_id="group_b",
        game_dir=Path("/tmp"),
        game_state={},
        result={"winner": "cop"},
        start_timestamp="2026-07-20T00:00:00",
        end_timestamp="2026-07-20T01:00:00",
        config_hash="abc123",
        log_hash="def456",
        required_files={},
        optional_files={},
    )

    # Try to modify (should raise)
    with pytest.raises(AttributeError):
        context.game_id = "modified"


def test_report_result_ok_true():
    """ReportResult with ok=True."""
    result = ReportResult(
        plugin="test",
        ok=True,
        status="completed",
        destination="/path/to/file",
    )

    assert result.ok is True
    assert result.status == "completed"
    assert result.error is None


def test_report_result_ok_false_with_error():
    """ReportResult with ok=False should have error."""
    result = ReportResult(
        plugin="test",
        ok=False,
        status="failed",
        error="Test error",
        error_code="test_error",
    )

    assert result.ok is False
    assert result.error == "Test error"
    assert result.error_code == "test_error"


def test_report_result_ok_false_without_error():
    """ReportResult with ok=False but no error should set default."""
    result = ReportResult(
        plugin="test",
        ok=False,
        status="failed",
    )

    assert result.ok is False
    assert result.error == "Unknown error"


def test_report_context_with_metadata():
    """ReportContext can include metadata."""
    metadata = {"custom_key": "custom_value", "version": 1}

    context = ReportContext(
        game_id="test_001",
        role="cop",
        group_id="group_a",
        opponent_group_id=None,
        game_dir=Path("/tmp"),
        game_state={},
        result=None,
        start_timestamp="2026-07-20T00:00:00",
        end_timestamp="2026-07-20T01:00:00",
        config_hash=None,
        log_hash=None,
        required_files={},
        optional_files={},
        metadata=metadata,
    )

    assert context.metadata["custom_key"] == "custom_value"
    assert context.metadata["version"] == 1
