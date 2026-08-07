"""Counted reliability acceptance: bounded retry and durable technical loss."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from agent.peer_turn_helpers import _bounded_exchange

from agent.mcp.coordinator import ProtocolCoordinator
from agent.mcp.protocol import ProtocolState
from agent.mcp.session_registry import SessionRegistry
from agent.reliability.deadline_tracker import DeadlineTracker
from agent.reliability.durable_io import PersistenceError, atomic_write_json


class _Runtime:
    game_id = "series_g01"
    counted_mode = True

    def __init__(self, tracker):
        self.orchestrator = SimpleNamespace(deadline_tracker=tracker)
        self.losses = []

    @staticmethod
    def _gamelet_number(_game_id):
        return 1

    def declare_technical_loss(self, reason, *, subsystem, step=0):
        self.losses.append((reason, subsystem, step))


@pytest.mark.asyncio
async def test_live_exchange_retries_idempotently_and_persists_success(tmp_path):
    tracker = DeadlineTracker(str(tmp_path / "deadlines.json"), timeout_s=5, max_attempts=3)
    runtime = _Runtime(tracker)
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TimeoutError("transient")
        return {"ok": True, "game_id": runtime.game_id}

    assert await _bounded_exchange(runtime, "commit", 1, flaky) == {
        "ok": True,
        "game_id": runtime.game_id,
    }
    assert calls == 3
    persisted = json.loads((tmp_path / "deadlines.json").read_text(encoding="utf-8"))
    assert persisted["records"][0]["terminal_status"] == "SUCCESS"
    assert runtime.losses == []


@pytest.mark.asyncio
async def test_live_exchange_exhaustion_routes_controlled_technical_loss(tmp_path):
    tracker = DeadlineTracker(str(tmp_path / "deadlines.json"), timeout_s=5, max_attempts=2)
    runtime = _Runtime(tracker)

    async def unavailable():
        raise ConnectionError("offline")

    with pytest.raises(ConnectionError, match="offline"):
        await _bounded_exchange(runtime, "reveal", 4, unavailable)
    assert runtime.losses[-1][1:] == ("peer_deadline", 4)


def test_durable_write_has_bounded_retries(monkeypatch, tmp_path):
    import agent.reliability.durable_io as durable

    real_replace = durable.os.replace
    calls = 0

    def flaky_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("injected")
        real_replace(source, destination)

    monkeypatch.setattr(durable.os, "replace", flaky_replace)
    path = tmp_path / "evidence.json"
    atomic_write_json(path, {"ok": True})
    assert calls == 3
    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_durable_write_fails_closed_after_bound(monkeypatch, tmp_path):
    import agent.reliability.durable_io as durable

    monkeypatch.setattr(
        durable.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("disk"))
    )
    with pytest.raises(PersistenceError, match="durable write failed"):
        atomic_write_json(tmp_path / "never.json", {"ok": False})


def test_coordinator_persists_technical_loss(tmp_path):
    registry = SessionRegistry()
    coordinator = ProtocolCoordinator(registry)
    evidence = tmp_path / "technical_loss.json"
    coordinator.on_handshake_complete("series_g01", 1, "cop")
    coordinator.on_technical_loss(
        "series_g01",
        1,
        "cop",
        reason="journal failed",
        evidence={"subsystem": "step_journal", "step": 2},
        evidence_path=str(evidence),
    )
    assert coordinator.get_state("series_g01", 1, "cop") == ProtocolState.TECHNICAL_LOSS
    saved = json.loads(evidence.read_text(encoding="utf-8"))
    assert saved["protocol_state"] == "technical_loss"
    assert saved["evidence"] == {"step": 2, "subsystem": "step_journal"}
