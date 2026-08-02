"""Tests that audit failure triggers TECHNICAL_LOSS in GameRunner."""

from unittest.mock import AsyncMock, patch

import pytest

from agent.game_runner import GameRunner


class TestTechnicalLossOnAuditFailure:
    def _make_runner(self, tmp_path):
        return GameRunner(
            cop_url="http://localhost:5000",
            thief_url="http://localhost:5001",
            secret="test-secret",
            config_sha256="a" * 64,
            games_dir=tmp_path / "memory",
        )

    @pytest.mark.asyncio
    async def test_audit_failure_sets_technical_loss(self, tmp_path):
        runner = self._make_runner(tmp_path)
        game_id = "test_tl_001"
        runner._game_id = game_id
        runner._game_dir = tmp_path / "memory" / game_id
        runner._game_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch(
                "agent.game_runner.final_audit",
                new=AsyncMock(return_value=(False, {"cop_step_1": "mismatch"})),
            ),
            patch("agent.game_runner.run_turn_loop", new=AsyncMock(return_value=("cop", None, 5))),
            patch("agent.game_runner.GameInitiator"),
            patch("agent.game_runner.generate_output_files", new=AsyncMock()),
            patch.object(runner, "_notify_game_end", new=AsyncMock()),
            patch.object(runner, "_save_game_state"),
            patch.object(runner, "_write_events"),
            patch.object(runner, "_handshake", new=AsyncMock(return_value=True)),
        ):
            result = await runner.run_game(game_id=game_id)

        assert result["winner"] == "TECHNICAL_LOSS", (
            f"Expected TECHNICAL_LOSS when audit fails, got {result['winner']}"
        )
        assert result["audit_ok"] is False

    @pytest.mark.asyncio
    async def test_audit_ok_preserves_original_winner(self, tmp_path):
        runner = self._make_runner(tmp_path)

        with (
            patch("agent.game_runner.final_audit", new=AsyncMock(return_value=(True, {}))),
            patch(
                "agent.game_runner.run_turn_loop", new=AsyncMock(return_value=("thief", None, 10))
            ),
            patch.object(runner, "_handshake", new=AsyncMock(return_value=True)),
            patch("agent.game_runner.generate_output_files", new=AsyncMock()),
            patch.object(runner, "_notify_game_end", new=AsyncMock()),
            patch.object(runner, "_save_game_state"),
            patch.object(runner, "_write_events"),
        ):
            result = await runner.run_game()

        assert result["winner"] == "thief"
        assert result["audit_ok"] is True
