"""Tests for the Watchdog module — independent heartbeat-based process monitor."""

import contextlib
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cop_worker.reliability.watchdog import (
    HeartbeatRecord,
    _read_heartbeat,
    _write_failure_evidence,
    run_watchdog,
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


class TestRunWatchdog:
    def test_kills_process_on_stale_heartbeat(self, hb_path, ev_path):
        """Run watchdog in a thread; verify os.kill is called when heartbeat is stale."""
        killed_pids = []

        def fake_kill(pid, sig):
            killed_pids.append(pid)

        # Write a heartbeat that is already stale
        write_heartbeat(hb_path, pid=9999, game_uid="g", session_id="s", step=1, state_path="/s")
        # Backdate the monotonic timestamp so it looks stale
        data = json.loads(Path(hb_path).read_text())
        data["last_heartbeat_monotonic"] = time.monotonic() - 999.0
        Path(hb_path).write_text(json.dumps(data))

        def _watchdog_runner():
            original_sleep = time.sleep
            call_count = [0]

            def fast_sleep(s):
                call_count[0] += 1
                if call_count[0] >= 2:
                    raise SystemExit(0)
                original_sleep(0.01)

            with (
                patch("cop_worker.reliability.watchdog.time.sleep", fast_sleep),
                patch("cop_worker.reliability.watchdog.os.kill", fake_kill),
                contextlib.suppress(SystemExit),
            ):
                run_watchdog(hb_path, ev_path, threshold_s=0.1)

        t = threading.Thread(target=_watchdog_runner, daemon=True)
        t.start()
        t.join(timeout=5.0)

        assert 9999 in killed_pids, f"Expected pid 9999 to be killed, got: {killed_pids}"

    def test_does_not_kill_on_fresh_heartbeat(self, hb_path, ev_path):
        """Watchdog should NOT kill when heartbeat is fresh."""
        killed_pids = []

        def fake_kill(pid, sig):
            killed_pids.append(pid)

        # Write a fresh heartbeat
        write_heartbeat(hb_path, pid=8888, game_uid="g", session_id="s", step=1, state_path="/s")

        def _watchdog_runner():
            original_sleep = time.sleep
            call_count = [0]

            def fast_sleep(s):
                call_count[0] += 1
                if call_count[0] >= 2:
                    raise SystemExit(0)
                original_sleep(0.01)

            with (
                patch("cop_worker.reliability.watchdog.time.sleep", fast_sleep),
                patch("cop_worker.reliability.watchdog.os.kill", fake_kill),
                contextlib.suppress(SystemExit),
            ):
                run_watchdog(hb_path, ev_path, threshold_s=100.0)

        t = threading.Thread(target=_watchdog_runner, daemon=True)
        t.start()
        t.join(timeout=5.0)

        assert killed_pids == [], f"Expected no kills, got: {killed_pids}"
