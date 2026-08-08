"""Fast unit tests for protocol detection and worker lifecycle health checks.

Network calls (urllib) are monkeypatched — no real sockets, no processes.
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from league_manager import worker_lifecycle as wl_mod
from league_manager.protocol.detection import ProtocolDetectionError, detect_protocol
from league_manager.worker_lifecycle import WorkerLifecycle, WorkerStartupError


class _Resp:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode()

    def read(self):
        return self._p


class _FakeAdapter:
    PROTOCOL_NAME = "reference-v3"

    @classmethod
    def candidate_tool_names(cls):
        return {"action"}


def _patch_urlopen(monkeypatch, router):
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: router(url))


# --- detection --------------------------------------------------------------


def test_detect_protocol_happy_path(monkeypatch):
    def router(url):
        if url.endswith("/tools"):
            return _Resp({"tools": ["action", "start_game"]})
        return _Resp({"protocol": "reference-v3"})

    _patch_urlopen(monkeypatch, router)
    adapter = detect_protocol("http://peer", adapter_classes=[_FakeAdapter])
    assert isinstance(adapter, _FakeAdapter)


def test_detect_protocol_discovery_failure(monkeypatch):
    def router(url):
        raise OSError("connection refused")

    _patch_urlopen(monkeypatch, router)
    with pytest.raises(ProtocolDetectionError, match="discovery failed"):
        detect_protocol("http://peer", adapter_classes=[_FakeAdapter])


def test_detect_protocol_no_candidate_match(monkeypatch):
    _patch_urlopen(monkeypatch, lambda url: _Resp({"tools": ["unrelated"]}))
    with pytest.raises(ProtocolDetectionError, match="No candidate"):
        detect_protocol("http://peer", adapter_classes=[_FakeAdapter])


def test_detect_protocol_version_mismatch(monkeypatch):
    def router(url):
        if url.endswith("/tools"):
            return _Resp({"tools": ["action"]})
        return _Resp({"protocol": "some-other-protocol"})

    _patch_urlopen(monkeypatch, router)
    with pytest.raises(ProtocolDetectionError, match="version metadata"):
        detect_protocol("http://peer", adapter_classes=[_FakeAdapter])


# --- worker lifecycle -------------------------------------------------------


def test_is_alive_true_when_health_responds(monkeypatch):
    _patch_urlopen(monkeypatch, lambda url: _Resp({"ok": True}))
    wl = WorkerLifecycle()
    assert wl.is_alive("cop") is True
    assert wl.is_alive("thief") is True


def test_is_alive_false_when_health_unreachable(monkeypatch):
    def boom(url):
        raise OSError("no route")

    _patch_urlopen(monkeypatch, boom)
    assert WorkerLifecycle().is_alive("cop") is False


def test_lifecycle_defaults():
    wl = WorkerLifecycle()
    assert wl._cop_url.endswith("8001") and wl._thief_url.endswith("8002")
    assert wl._cop_proc is None and wl._thief_proc is None


def test_ensure_ready_skips_start_when_already_alive(monkeypatch):
    wl = WorkerLifecycle()
    monkeypatch.setattr(wl, "is_alive", lambda role: True)
    started = []
    monkeypatch.setattr(wl, "_start_worker", lambda role: started.append(role))
    wl.ensure_ready(timeout=0.1)
    assert started == []  # both already alive → no starts


def test_stop_all_terminates_started_processes():
    wl = WorkerLifecycle()

    class _Proc:
        def __init__(self):
            self.terminated = False

        def terminate(self):
            self.terminated = True

    wl._cop_proc = _Proc()
    wl._thief_proc = _Proc()
    wl.stop_all()
    assert wl._cop_proc.terminated and wl._thief_proc.terminated


def test_start_worker_launches_subprocess(monkeypatch):
    wl = WorkerLifecycle()

    class _FakePopen:
        def __init__(self, cmd, **kw):
            self.cmd = cmd

    monkeypatch.setattr(wl_mod.subprocess, "Popen", _FakePopen)
    wl._start_worker("cop")
    assert isinstance(wl._cop_proc, _FakePopen)


def test_wait_for_worker_times_out(monkeypatch):
    wl = WorkerLifecycle()
    monkeypatch.setattr(wl, "is_alive", lambda role: False)
    with pytest.raises(WorkerStartupError):
        wl._wait_for_worker("cop", timeout=0)  # deadline already passed → immediate raise
