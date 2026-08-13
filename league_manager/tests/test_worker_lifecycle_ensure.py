"""Cover ensure_ready, _start_worker, and _wait_for_worker in WorkerLifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from league_manager.worker_lifecycle import WorkerLifecycle, WorkerStartupError


def test_ensure_ready_starts_and_waits():
    wl = WorkerLifecycle()
    # Per role: the ensure-check sees a dead worker, the wait-check sees it alive.
    liveness = iter([False, True, False, True])
    with (
        patch.object(wl, "is_alive", side_effect=lambda role: next(liveness)),
        patch("league_manager.worker_lifecycle.subprocess.Popen") as popen,
    ):
        popen.return_value = MagicMock()
        wl.ensure_ready(timeout=5.0)
    assert popen.call_count == 2  # cop and thief both launched
    assert wl._cop_proc is not None and wl._thief_proc is not None


def test_ensure_ready_skips_already_alive_workers():
    wl = WorkerLifecycle()
    with (
        patch.object(wl, "is_alive", return_value=True),
        patch("league_manager.worker_lifecycle.subprocess.Popen") as popen,
    ):
        wl.ensure_ready(timeout=1.0)
    popen.assert_not_called()


def test_start_worker_thief_stores_process():
    wl = WorkerLifecycle()
    with patch("league_manager.worker_lifecycle.subprocess.Popen") as popen:
        popen.return_value = MagicMock()
        wl._start_worker("thief")
    assert wl._thief_proc is not None
    assert wl._cop_proc is None


def test_wait_for_worker_times_out():
    wl = WorkerLifecycle()
    with (
        patch.object(wl, "is_alive", return_value=False),
        pytest.raises(WorkerStartupError, match="did not start"),
    ):
        wl._wait_for_worker("cop", timeout=0.0)
