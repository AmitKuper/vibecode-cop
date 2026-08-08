"""Tests for DeadlineTracker — bounded external request tracking."""

import json
import time
from pathlib import Path

import pytest

from league_manager.reliability.deadline_tracker import DeadlineTracker


@pytest.fixture
def tracker_path(tmp_path):
    return str(tmp_path / "deadlines.json")


@pytest.fixture
def tracker(tracker_path):
    return DeadlineTracker(tracker_path, timeout_s=10.0, max_attempts=3)


def _begin(tracker, phase="commit", step=1):
    return tracker.begin(
        idempotency_key="ikey-1",
        game_uid="game-abc",
        gamelet=0,
        step=step,
        phase=phase,
    )


class TestBegin:
    def test_creates_record_with_correct_expiry(self, tracker):
        before = time.monotonic()
        rec = _begin(tracker)
        after = time.monotonic()

        assert rec.expiry_monotonic >= before + 10.0
        assert rec.expiry_monotonic <= after + 10.0

    def test_record_fields_set(self, tracker):
        rec = _begin(tracker, phase="reveal", step=3)
        assert rec.game_uid == "game-abc"
        assert rec.gamelet == 0
        assert rec.step == 3
        assert rec.phase == "reveal"
        assert rec.attempt == 0
        assert rec.terminal_status == ""
        assert rec.request_id != ""

    def test_saves_to_disk(self, tracker, tracker_path):
        rec = _begin(tracker)
        data = json.loads(Path(tracker_path).read_text())
        assert any(r["request_id"] == rec.request_id for r in data["records"])


class TestComplete:
    def test_marks_terminal_success(self, tracker):
        rec = _begin(tracker)
        tracker.complete(rec.request_id, status="SUCCESS", response_digest="abc123")
        loaded = tracker.get(rec.request_id)
        assert loaded.terminal_status == "SUCCESS"
        assert loaded.response_digest == "abc123"
        assert loaded.is_terminal()

    def test_noop_for_unknown_id(self, tracker):
        # Should not raise
        tracker.complete("nonexistent-id")


class TestFail:
    def test_increments_attempt_and_returns_true(self, tracker):
        rec = _begin(tracker)
        should_retry = tracker.fail(rec.request_id, error="network error")
        assert should_retry is True
        updated = tracker.get(rec.request_id)
        assert updated.attempt == 1
        assert updated.last_error == "network error"

    def test_returns_false_at_max_attempts(self, tracker):
        rec = _begin(tracker)
        # max_attempts=3, so fail 3 times
        tracker.fail(rec.request_id, "err")
        tracker.fail(rec.request_id, "err")
        result = tracker.fail(rec.request_id, "err")
        assert result is False
        updated = tracker.get(rec.request_id)
        assert updated.terminal_status == "PERMANENT_FAIL"

    def test_returns_false_on_expired_record(self, tracker_path):
        # Use a tracker with near-zero timeout
        t = DeadlineTracker(tracker_path, timeout_s=0.001, max_attempts=10)
        rec = t.begin("ik", "g", 0, 1, "commit")
        time.sleep(0.05)  # let it expire
        result = t.fail(rec.request_id, "timeout")
        assert result is False
        updated = t.get(rec.request_id)
        assert updated.terminal_status == "TIMEOUT"

    def test_returns_false_for_unknown_id(self, tracker):
        assert tracker.fail("bad-id", "err") is False


class TestPendingExpired:
    def test_returns_only_expired_non_terminal(self, tracker_path):
        t_fast = DeadlineTracker(tracker_path, timeout_s=0.01, max_attempts=3)
        rec_fast = t_fast.begin("ik1", "g", 0, 1, "commit")
        rec_long = t_fast.begin("ik2", "g", 0, 2, "commit")

        # Manually extend the long record's expiry so it won't expire
        t_fast._records[rec_long.request_id].expiry_monotonic = time.monotonic() + 9999
        t_fast._save()

        time.sleep(0.05)
        expired = t_fast.pending_expired()
        ids = {r.request_id for r in expired}
        assert rec_fast.request_id in ids
        assert rec_long.request_id not in ids

    def test_excludes_terminal_records(self, tracker_path):
        t = DeadlineTracker(tracker_path, timeout_s=0.01, max_attempts=3)
        rec = t.begin("ik", "g", 0, 1, "commit")
        t.complete(rec.request_id, "SUCCESS")
        time.sleep(0.05)
        assert t.pending_expired() == []


class TestPersistence:
    def test_save_and_reload(self, tracker_path):
        t1 = DeadlineTracker(tracker_path, timeout_s=10.0, max_attempts=3)
        rec = t1.begin("ik", "g", 0, 1, "commit")
        t1.complete(rec.request_id, "SUCCESS")

        t2 = DeadlineTracker(tracker_path, timeout_s=10.0, max_attempts=3)
        loaded = t2.get(rec.request_id)
        assert loaded is not None
        assert loaded.terminal_status == "SUCCESS"
        assert loaded.game_uid == "g"

    def test_atomic_write_no_partial_reads(self, tracker_path):
        """Verify .tmp is used and replaced atomically."""
        tracker = DeadlineTracker(tracker_path, timeout_s=10.0, max_attempts=3)
        _begin(tracker)
        # After save, .tmp file should NOT remain
        tmp_path = tracker_path + ".tmp"
        assert not Path(tmp_path).exists()
        # Main file must exist and be valid JSON
        data = json.loads(Path(tracker_path).read_text())
        assert "records" in data
