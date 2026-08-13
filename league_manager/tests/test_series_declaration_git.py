"""Cover git-SHA, clean-check, and hardware-info helpers in series_declaration."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from league_manager.step0 import series_declaration as sd


def _run_result(returncode=0, stdout="", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_get_git_sha_success():
    with patch.object(sd.subprocess, "run", return_value=_run_result(stdout="deadbeef\n")):
        assert sd.get_git_sha() == "deadbeef"


def test_get_git_sha_failure_raises():
    with (
        patch.object(sd.subprocess, "run", return_value=_run_result(1, stderr="boom")),
        pytest.raises(RuntimeError, match="git rev-parse failed"),
    ):
        sd.get_git_sha()


def test_is_git_clean_true_and_false():
    with patch.object(sd.subprocess, "run", return_value=_run_result(stdout="")):
        assert sd.is_git_clean() is True
    with patch.object(sd.subprocess, "run", return_value=_run_result(stdout=" M file.py")):
        assert sd.is_git_clean() is False


def test_get_hardware_info_reads_cpu_frequency(monkeypatch):
    fake_psutil = types.ModuleType("psutil")
    fake_psutil.cpu_freq = lambda: MagicMock(max=2400.0)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    info = sd.get_hardware_info()
    assert info["cpu_frequency_ghz"] == 2.4
    assert "cpu_model" in info and info["gpu_model"] == "unknown"
