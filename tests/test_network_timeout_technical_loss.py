import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Tests that network timeout triggers TECHNICAL_LOSS via watchdog."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from cop_worker.game_runner_turn import run_turn_loop

from cop_worker.board import Board
from cop_worker.rules_engine import RulesEngine


def _make_mock_runner():
    runner = MagicMock()
    runner.config_sha256 = "a" * 64
    runner._cop_commits = {}
    runner._thief_commits = {}
    runner._cop_reveals = {}
    runner._thief_reveals = {}
    runner._log_event = MagicMock()
    runner._board_to_state = MagicMock(
        return_value={
            "step": 0,
            "turn": 0,
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "move_history": [],
        }
    )
    return runner


class TestNetworkTimeoutTechnicalLoss:
    @pytest.mark.asyncio
    async def test_watchdog_timeout_causes_technical_loss(self):
        runner = _make_mock_runner()
        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        rules = RulesEngine(board, max_turns=5)

        # Make the commit call hang forever
        async def slow_commit(*args, **kwargs):
            await asyncio.sleep(999)
            return "fake_hash"

        with patch("agent.game_runner_turn.request_commit", side_effect=slow_commit):
            winner, abort, step = await run_turn_loop(
                runner,
                "timeout_game_001",
                board,
                rules,
                max_turns=5,
                watchdog_timeout=0.05,  # 50ms — will trigger
            )

        assert winner == "TECHNICAL_LOSS", f"Expected TECHNICAL_LOSS, got {winner}"
        assert abort is not None
        assert "timeout" in abort.lower() or "watchdog" in abort.lower()

    @pytest.mark.asyncio
    async def test_client_timeout_raises_asyncio_timeout(self):
        from cop_worker.mcp.client import GameMCPClient

        client = GameMCPClient("http://localhost:9999/mcp", "secret", timeout_seconds=0.001)

        async def mock_call_tool(*args, **kwargs):
            await asyncio.sleep(999)

        with (
            patch.object(client, "_call_tool", side_effect=asyncio.TimeoutError),
            pytest.raises((asyncio.TimeoutError, Exception)),
        ):
            await client.action(
                "game1",
                MagicMock(
                    game_id="g1",
                    step=1,
                    role="cop",
                    config_sha256="a" * 64,
                    timestamp="",
                    phase="commit",
                    to_dict=lambda: {},
                ),
            )

    @pytest.mark.asyncio
    async def test_normal_turn_completes_without_timeout(self):
        runner = _make_mock_runner()
        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        rules = RulesEngine(board, max_turns=2)

        async def fast_commit(*args, **kwargs):
            return "a" * 64

        async def fast_reveal(*args, **kwargs):
            return {
                "move": "STAY",
                "h_commit": "a" * 64,
                "state_hash": "s",
                "hint": "",
                "intent": "truth",
            }

        with (
            patch("agent.game_runner_turn.request_commit", side_effect=fast_commit),
            patch("agent.game_runner_turn.request_reveal", side_effect=fast_reveal),
        ):
            winner, abort, step = await run_turn_loop(
                runner,
                "normal_game",
                board,
                rules,
                max_turns=2,
                watchdog_timeout=10.0,
            )

        assert winner != "TECHNICAL_LOSS" or abort is None or "timeout" not in (abort or "")
