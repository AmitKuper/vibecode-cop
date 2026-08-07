"""Tests for cop_worker reliability — DeadlineTracker."""

import tempfile
from pathlib import Path

from cop_worker.reliability.deadline_tracker import DeadlineTracker


def make_tracker(timeout_s=60.0, tmp_path=None) -> DeadlineTracker:
    """Create a DeadlineTracker backed by a temp file."""
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp()) / "deadlines.json"
    return DeadlineTracker(str(tmp_path), timeout_s=timeout_s)


def test_begin_returns_deadline_record(tmp_path):
    """begin() must return a DeadlineRecord."""
    dt = make_tracker(tmp_path=tmp_path / "d.json")
    rec = dt.begin("ikey_001", "game_001", 1, 1, "commit")
    assert rec is not None
    assert rec.game_uid == "game_001"
    assert rec.phase == "commit"


def test_is_not_expired_immediately(tmp_path):
    """A new record with 60s timeout must not be expired immediately."""
    dt = make_tracker(timeout_s=60.0, tmp_path=tmp_path / "d.json")
    rec = dt.begin("ikey_002", "game_002", 1, 1, "commit")
    assert rec.is_expired() is False


def test_complete_marks_record_terminal(tmp_path):
    """complete() must mark the record with terminal_status=SUCCESS."""
    dt = make_tracker(tmp_path=tmp_path / "d.json")
    rec = dt.begin("ikey_003", "game_003", 1, 1, "reveal")
    dt.complete(rec.request_id, status="SUCCESS")
    retrieved = dt.get(rec.request_id)
    assert retrieved is not None
    assert retrieved.terminal_status == "SUCCESS"
    assert retrieved.is_terminal() is True


def test_fail_marks_attempt(tmp_path):
    """fail() must increment attempt count."""
    dt = make_tracker(tmp_path=tmp_path / "d.json", timeout_s=60.0)
    rec = dt.begin("ikey_004", "game_004", 1, 1, "audit")
    dt.fail(rec.request_id, "timeout")
    updated = dt.get(rec.request_id)
    assert updated.attempt == 1
