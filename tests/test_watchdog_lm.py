"""Tests for the Watchdog module — independent heartbeat-based process monitor."""

import json
import time
from pathlib import Path

import pytest

from league_manager.reliability.watchdog import (
    HeartbeatRecord,
    _read_heartbeat,
    _write_failure_evidence,
    write_heartbeat,
)


@pytest.fixture
def hb_path(tmp_path):
    return str(tmp_path / "heartbeat.json")


@pytest.fixture
def ev_path(tmp_path):
    return str(tmp_path / "failure_evidence.json")


class TestWriteHeartbeat:
    def test_creates_valid_json_file(self, hb_path):
        write_heartbeat(
            hb_path, pid=1234, game_uid="g1", session_id="s1", step=5, state_path="/tmp/st"
        )
        data = json.loads(Path(hb_path).read_text())
        assert data["pid"] == 1234
        assert data["game_uid"] == "g1"
        assert data["session_id"] == "s1"
        assert data["current_step"] == 5
        assert data["state_path"] == "/tmp/st"
        assert "last_heartbeat_utc" in data
        assert "last_heartbeat_monotonic" in data

    def test_no_tmp_file_remains(self, hb_path):
        write_heartbeat(hb_path, pid=42, game_uid="g", session_id="s", step=0, state_path="/s")
        assert not Path(hb_path + ".tmp").exists()

    def test_overwrites_existing(self, hb_path):
        write_heartbeat(hb_path, pid=1, game_uid="g", session_id="s", step=1, state_path="/s")
        write_heartbeat(hb_path, pid=2, game_uid="g", session_id="s", step=2, state_path="/s")
        data = json.loads(Path(hb_path).read_text())
        assert data["pid"] == 2
        assert data["current_step"] == 2


class TestReadHeartbeat:
    def test_returns_none_for_missing_file(self, hb_path):
        result = _read_heartbeat(hb_path)
        assert result is None

    def test_returns_none_for_corrupt_json(self, hb_path):
        Path(hb_path).write_text("not-valid-json{{")
        result = _read_heartbeat(hb_path)
        assert result is None

    def test_returns_record_for_valid_file(self, hb_path):
        write_heartbeat(hb_path, pid=99, game_uid="g2", session_id="s2", step=3, state_path="/x")
        rec = _read_heartbeat(hb_path)
        assert isinstance(rec, HeartbeatRecord)
        assert rec.pid == 99
        assert rec.game_uid == "g2"


class TestWriteFailureEvidence:
    def test_writes_expected_keys(self, ev_path):
        rec = HeartbeatRecord(
            pid=555,
            game_uid="game-x",
            session_id="sess-y",
            last_heartbeat_monotonic=time.monotonic() - 30,
            last_heartbeat_utc="2026-08-03T00:00:00Z",
            current_step=7,
            state_path="/st",
        )
        _write_failure_evidence(ev_path, rec, reason="Heartbeat stale for 30s > threshold 15s")
        data = json.loads(Path(ev_path).read_text())
        assert data["reason"].startswith("Heartbeat stale")
        assert data["pid"] == 555
        assert data["game_uid"] == "game-x"
        assert data["watchdog_action"] == "SIGTERM"
        assert "detected_utc" in data
        assert "last_heartbeat_utc" in data
