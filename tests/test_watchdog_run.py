"""Tests for the Watchdog run loop — kill-on-stale versus keep-alive-on-fresh."""

import contextlib
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cop_worker.reliability.watchdog import run_watchdog, write_heartbeat


@pytest.fixture
def hb_path(tmp_path):
    return str(tmp_path / "heartbeat.json")


@pytest.fixture
def ev_path(tmp_path):
    return str(tmp_path / "failure_evidence.json")


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
