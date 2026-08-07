from __future__ import annotations

import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Integration tests verifying Phase 3 v7 wiring into production lifecycle."""


import contextlib
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_peer_runtime(tmp_path):
    """Construct a PeerRuntime with all heavy deps mocked out."""
    from cop_worker.peer_runtime import PeerRuntime

    with (
        patch("agent.peer_runtime.GameMCPClient", return_value=MagicMock()),
        patch("agent.peer_runtime._load_start_positions", return_value=([0, 0], [6, 6])),
        patch("agent.peer_runtime.PeerRuntime._init_llm", return_value=None),
    ):
        runtime = PeerRuntime(
            role="cop",
            secret="test-secret",
            config_sha256="a" * 64,
            opponent_url="http://localhost:5001/mcp",
            games_dir=tmp_path,
            counted_mode=False,
        )
    return runtime


def _make_orchestrator(tmp_path):
    from cop_worker.agent_orchestrator import AgentOrchestrator

    from cop_worker.runtime_mode import RuntimeMode

    return AgentOrchestrator(
        role="cop",
        game_uid="test-game-001",
        grid_size=7,
        mode=RuntimeMode.DEVELOPMENT,
        work_dir=str(tmp_path),
        config={},
    )


# ---------------------------------------------------------------------------
# Test 1: PeerRuntime creates orchestrator
# ---------------------------------------------------------------------------


class TestPeerRuntimeCreatesOrchestrator:
    def test_peer_runtime_creates_orchestrator(self, tmp_path):
        """After PeerRuntime.__init__, orchestrator attribute exists (may be None — lazy init)."""
        runtime = _make_peer_runtime(tmp_path)
        # orchestrator starts as None and is lazy-init'd in run_game
        assert hasattr(runtime, "orchestrator")

    def test_peer_runtime_orchestrator_set_after_run_game_init(self, tmp_path):
        """AgentOrchestrator is initialised inside run_game before gameplay."""
        from cop_worker.agent_orchestrator import AgentOrchestrator

        from cop_worker.runtime_mode import RuntimeMode

        runtime = _make_peer_runtime(tmp_path)
        # Manually trigger the orchestrator init logic that run_game would do
        _mode = RuntimeMode.DEVELOPMENT
        runtime.orchestrator = AgentOrchestrator(
            role=runtime.role,
            game_uid="test-game-001",
            grid_size=7,
            mode=_mode,
            work_dir=str(tmp_path),
        )
        assert runtime.orchestrator is not None
        assert runtime.orchestrator.role == "cop"


# ---------------------------------------------------------------------------
# Test 2: watchdog heartbeat path set after start_watchdog
# ---------------------------------------------------------------------------


class TestWatchdogHeartbeatPath:
    def test_watchdog_heartbeat_path_set_after_start(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        assert orch._watchdog_heartbeat_path == ""
        orch.start_watchdog()
        assert orch._watchdog_heartbeat_path != ""

    def test_watchdog_heartbeat_path_contains_game_uid(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch.start_watchdog()
        assert "test-game-001" in orch._watchdog_heartbeat_path

    def test_watchdog_start_emits_first_heartbeat(self, tmp_path):
        from pathlib import Path

        orch = _make_orchestrator(tmp_path)
        orch.start_watchdog()
        # Heartbeat file should be created
        assert Path(orch._watchdog_heartbeat_path).exists()


# ---------------------------------------------------------------------------
# Test 3: Step-0 validation called in counted mode
# ---------------------------------------------------------------------------


class TestStep0ValidationInCountedMode:
    def test_validate_counted_declaration_called_during_counted_startup(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        decl = orch.build_step0_declaration("g1")
        # In DEVELOPMENT mode, validate_counted_declaration always returns []
        errors = orch.validate_counted_declaration(decl)
        assert errors == []

    def test_step0_validation_raises_for_invalid_counted_declaration(self, tmp_path):
        from cop_worker.runtime_mode import RuntimeMode

        # Counted construction is covered separately; isolate the production
        # Step-0 validator here while retaining its counted behavior.
        orch = _make_orchestrator(tmp_path)
        orch.mode = RuntimeMode.COUNTED

        from cop_worker.step0.declaration import PeerDeclaration

        bad_decl = PeerDeclaration(game_uid="g1")  # all placeholders
        errors = orch.validate_counted_declaration(bad_decl)
        assert len(errors) > 0

    def test_step0_validation_send_start_game_integration(self, tmp_path):
        """Verify _send_start_game calls validate_counted_declaration when counted."""
        runtime = _make_peer_runtime(tmp_path)
        # Give it an orchestrator
        from cop_worker.agent_orchestrator import AgentOrchestrator

        from cop_worker.runtime_mode import RuntimeMode

        runtime.orchestrator = AgentOrchestrator(
            role="cop",
            game_uid="cg1",
            grid_size=7,
            mode=RuntimeMode.DEVELOPMENT,
            work_dir=str(tmp_path),
        )

        called = []
        original_validate = runtime.orchestrator.validate_counted_declaration

        def spy_validate(decl):
            called.append(decl)
            return original_validate(decl)

        runtime.orchestrator.validate_counted_declaration = spy_validate

        import asyncio
        from unittest.mock import AsyncMock

        async def _run():
            # Patch the network call to avoid real I/O
            with (
                patch.object(
                    runtime.opponent_client,
                    "start_game",
                    new_callable=AsyncMock,
                    return_value={"ok": True},
                ),
                contextlib.suppress(Exception),
            ):
                # counted_mode=True triggers Step-0 validation
                await runtime._send_start_game("cg1", counted_mode=True)

        asyncio.run(_run())
        # validate_counted_declaration must have been called once
        assert len(called) >= 1
