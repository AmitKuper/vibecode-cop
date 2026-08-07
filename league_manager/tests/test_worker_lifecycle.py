"""Tests for WorkerLifecycle — using mock to avoid real subprocesses."""

from unittest.mock import MagicMock, patch

from league_manager.worker_lifecycle import WorkerLifecycle


def test_is_alive_returns_false_when_unreachable():
    """is_alive returns False when the worker URL is not reachable."""
    wl = WorkerLifecycle(cop_url="http://localhost:19999")
    assert wl.is_alive("cop") is False


def test_is_alive_returns_true_when_reachable():
    """is_alive returns True when urlopen succeeds."""
    wl = WorkerLifecycle()
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = MagicMock()
        assert wl.is_alive("cop") is True


def test_stop_all_terminates_started_processes():
    """stop_all calls terminate() on any process started by this manager."""
    wl = WorkerLifecycle()
    mock_proc = MagicMock()
    wl._cop_proc = mock_proc
    wl.stop_all()
    mock_proc.terminate.assert_called_once()
