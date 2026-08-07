"""Tests for SeriesJSONL append-only event log."""

import pytest

from league_manager.series_jsonl import VALID_EVENTS, SeriesJSONL


def test_append_and_read(tmp_path):
    """Single appended event is readable."""
    log = SeriesJSONL(tmp_path / "test.jsonl")
    log.append("series_created", "uid_001", "game_001")
    events = log.read_all()
    assert len(events) == 1
    assert events[0]["event"] == "series_created"


def test_append_multiple_events(tmp_path):
    """Multiple events are all stored and extra fields preserved."""
    log = SeriesJSONL(tmp_path / "test.jsonl")
    log.append("series_created", "uid_002", "game_002")
    log.append("gamelet_started", "uid_002", "game_002", sub_game_number=1)
    log.append("gamelet_settled", "uid_002", "game_002", sub_game_number=1, winner="police")
    events = log.read_all()
    assert len(events) == 3
    assert events[2]["winner"] == "police"


def test_invalid_event_raises(tmp_path):
    """Unknown event name raises ValueError."""
    log = SeriesJSONL(tmp_path / "test.jsonl")
    with pytest.raises(ValueError, match="Unknown event"):
        log.append("invalid_event_xyz", "uid_003", "game_003")


def test_read_empty_file(tmp_path):
    """Reading from a non-existent file returns empty list."""
    log = SeriesJSONL(tmp_path / "nonexistent.jsonl")
    assert log.read_all() == []


def test_event_has_timestamp(tmp_path):
    """Every appended event includes a timestamp field."""
    log = SeriesJSONL(tmp_path / "test.jsonl")
    log.append("series_created", "uid_004", "game_004")
    events = log.read_all()
    assert "timestamp" in events[0]


def test_all_valid_events_accepted(tmp_path):
    """Every event name in VALID_EVENTS can be appended without error."""
    log = SeriesJSONL(tmp_path / "test.jsonl")
    for event in sorted(VALID_EVENTS):
        log.append(event, "uid_005", "game_005")
    events = log.read_all()
    assert len(events) == len(VALID_EVENTS)
