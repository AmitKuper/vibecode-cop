from __future__ import annotations

import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Production turn evidence for nonce secrecy and canonical physics."""


from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cop_worker.board import Board
from cop_worker.rules_engine import RulesEngine


def _runtime(tmp_path):
    runtime = MagicMock()
    runtime.board = Board(cop_position=[0, 0], thief_position=[3, 3])
    runtime.role = "cop"
    runtime.game_id = "zero_trust_g01"
    runtime._cop_barriers_remaining = 14
    runtime._my_commits = {}
    runtime.config_sha256 = "c" * 64
    runtime.secret = "test-secret"
    runtime.counted_mode = False
    runtime.orchestrator = None
    runtime.protocol_adapter = None
    runtime.game_dir = tmp_path
    runtime._store_my_commit = lambda step, payload: runtime._my_commits.update({step: payload})
    return runtime


@pytest.mark.asyncio
async def test_live_reveal_excludes_nonce_and_uses_canonical_movement(tmp_path):
    from cop_worker.peer_turn_loop import run_peer_turn

    runtime = _runtime(tmp_path)
    rules = RulesEngine(runtime.board)
    reveal = AsyncMock(
        return_value={"move": "STAY", "hint": "waiting here", "intent": "truth", "state_hash": "x"}
    )
    with (
        patch("agent.peer_turn_loop.select_move", new=AsyncMock(return_value="E")),
        patch(
            "agent.peer_turn_loop.send_commit", new=AsyncMock(return_value={"h_commit": "a" * 64})
        ),
        patch("agent.peer_turn_loop.send_reveal", new=reveal),
        patch("agent.peer_turn_loop.append_opponent_commit"),
        patch("agent.peer_turn_loop.append_opponent_reveal"),
        patch("agent.peer_turn_loop.get_coordinator", return_value=MagicMock()),
        patch.object(rules, "apply_moves", side_effect=AssertionError("legacy physics called")),
    ):
        _winner, abort = await run_peer_turn(runtime, 1, rules)

    assert abort is None
    assert "nonce" not in reveal.await_args.args[2]
    assert runtime.board.cop_position == [1, 0]
    assert runtime.board.turn == 1


@pytest.mark.asyncio
async def test_invalid_peer_action_is_technical_abort_not_stay(tmp_path):
    from cop_worker.peer_turn_loop import run_peer_turn

    runtime = _runtime(tmp_path)
    rules = RulesEngine(runtime.board)
    before = runtime.board.to_dict()
    with (
        patch("agent.peer_turn_loop.select_move", new=AsyncMock(return_value="E")),
        patch(
            "agent.peer_turn_loop.send_commit", new=AsyncMock(return_value={"h_commit": "a" * 64})
        ),
        patch(
            "agent.peer_turn_loop.send_reveal",
            new=AsyncMock(
                return_value={
                    "move": "DIAGONAL",
                    "hint": "bad",
                    "intent": "truth",
                    "state_hash": "x",
                }
            ),
        ),
        patch("agent.peer_turn_loop.append_opponent_commit"),
        patch("agent.peer_turn_loop.append_opponent_reveal"),
        patch("agent.peer_turn_loop.get_coordinator", return_value=MagicMock()),
    ):
        winner, abort = await run_peer_turn(runtime, 1, rules)

    assert winner is None
    assert "illegal thief action" in abort
    assert runtime.board.to_dict() == before


def test_passive_invalid_peer_action_rejected_without_board_mutation(tmp_path):
    from cop_worker.peer_agent_passive import handle_passive_reveal, init_passive_game
    from cop_worker.peer_runtime import PeerRuntime

    runtime = PeerRuntime(
        role="thief",
        secret="test-secret",
        config_sha256="c" * 64,
        opponent_url="http://127.0.0.1:65530/mcp",
        games_dir=tmp_path,
    )
    rules_ref = []
    init_passive_game(runtime, "zero_trust_g01", rules_ref)
    runtime._my_commits[1] = {
        "move": "STAY",
        "hint": "waiting here",
        "intent": "truth",
        "state_hash": "x",
        "nonce": "secret",
    }
    before = runtime.board.to_dict()
    result = handle_passive_reveal(
        runtime,
        "zero_trust_g01",
        SimpleNamespace(step=1, move="DIAGONAL", hint="bad", intent="truth", state_hash="x"),
        rules_ref,
    )
    assert result["ok"] is False
    assert "Protocol violation" in result["error"]
    assert runtime.board.to_dict() == before
