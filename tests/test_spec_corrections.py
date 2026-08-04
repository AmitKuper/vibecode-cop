"""Phase 0 spec-correction acceptance tests.

Verifies the binding rules restored in Phase 0:
  - 0.1 Trapped-thief: STAY does not count as an orthogonal escape
  - 0.2 Barrier-on-thief: placing a barrier on the thief's cell is capture
  - 0.3 Audit completeness: empty commitment log => NOT_APPLICABLE, not success
  - 0.4 Exactly six gamelets: five and seven are rejected in counted mode
  - 0.5 No LLM movement: select_move must not call LLM when RL fails
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.board import Board
from agent.game_series import GameSeries
from agent.rules_engine import GameOutcome, RulesEngine
from agent.rules_outcomes import check_game_status

# ---------------------------------------------------------------------------
# 0.1 Trapped-thief semantics
# ---------------------------------------------------------------------------


class TestTrappedThiefSemantics:
    def _surrounded_board(self) -> Board:
        """Thief at [1,1] with barriers on all four orthogonal neighbours."""
        board = Board(cop_position=[0, 0], thief_position=[1, 1])
        board.barriers = [[1, 0], [1, 2], [0, 1], [2, 1]]
        return board

    def test_has_orthogonal_escape_returns_false_when_surrounded(self):
        board = self._surrounded_board()
        assert board.has_orthogonal_escape("thief") is False

    def test_has_orthogonal_escape_returns_true_when_one_exit(self):
        board = Board(cop_position=[0, 0], thief_position=[1, 1])
        board.barriers = [[1, 0], [0, 1], [2, 1]]  # SOUTH open
        assert board.has_orthogonal_escape("thief") is True

    def test_surrounded_thief_is_cop_win(self):
        board = self._surrounded_board()
        outcome = check_game_status(board, max_turns=35)
        assert outcome == GameOutcome.COP_WIN

    def test_stay_only_thief_is_cop_win(self):
        """Thief surrounded on all sides — STAY does not rescue it."""
        board = self._surrounded_board()
        rules = RulesEngine(board)
        assert rules.check_game_status() == GameOutcome.COP_WIN

    def test_thief_at_corner_with_barriers_is_cop_win(self):
        """Thief in corner [0,0], barriers at [1,0] and [0,1] => trapped."""
        board = Board(cop_position=[3, 3], thief_position=[0, 0])
        board.barriers = [[1, 0], [0, 1]]
        assert board.has_orthogonal_escape("thief") is False
        assert check_game_status(board, max_turns=35) == GameOutcome.COP_WIN

    def test_thief_at_edge_with_one_exit(self):
        """Thief at [0,1] (left edge), barrier at [0,0] and [0,2], exit at [1,1]."""
        board = Board(cop_position=[3, 3], thief_position=[0, 1])
        board.barriers = [[0, 0], [0, 2]]
        assert board.has_orthogonal_escape("thief") is True
        assert check_game_status(board, max_turns=35) == GameOutcome.ONGOING

    def test_unsurrounded_thief_is_ongoing(self):
        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        assert check_game_status(board, max_turns=35) == GameOutcome.ONGOING


# ---------------------------------------------------------------------------
# 0.2 Barrier-on-thief capture
# ---------------------------------------------------------------------------


class TestBarrierOnThiefCapture:
    def test_barrier_on_thief_cell_is_capture(self):
        """Board.is_capture() must return True after placing a barrier on thief's cell."""
        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        placed = board.place_barrier(3, 3)
        assert placed is True, "place_barrier must succeed on thief's cell"
        assert board.is_capture() is True

    def test_barrier_on_thief_is_cop_win(self):
        """check_game_status must return COP_WIN when thief is on a barrier cell."""
        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        board.place_barrier(3, 3)
        assert check_game_status(board, max_turns=35) == GameOutcome.COP_WIN

    def test_env_helper_places_barrier_on_thief(self):
        """apply_place_action must no longer skip the thief's current cell."""
        from agent.rl.env_helpers import apply_place_action

        board = Board(cop_position=[2, 3], thief_position=[2, 2])
        # Cop at [2,3], PLACE_N places barrier at [2,2] which is the thief's position.
        barriers_before = 5
        barriers_after = apply_place_action(board, "PLACE_N", board.grid_size, barriers_before)
        assert barriers_after == barriers_before - 1, "Barrier must have been placed"
        assert board.is_capture() is True, "Placing barrier on thief must be capture"

    def test_barrier_not_placed_outside_grid(self):
        """apply_place_action must still reject out-of-bounds placement."""
        from agent.rl.env_helpers import apply_place_action

        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        result = apply_place_action(board, "PLACE_N", board.grid_size, 5)
        assert result == 5  # no barrier consumed (out of bounds)


# ---------------------------------------------------------------------------
# 0.3 Audit completeness
# ---------------------------------------------------------------------------


class TestAuditCompleteness:
    def test_empty_commits_returns_not_applicable(self, tmp_path):
        """run_final_audit with no commits must return (False, NOT_APPLICABLE)."""
        from agent.peer_audit import run_final_audit

        game_dir = tmp_path / "game"
        game_dir.mkdir()
        ok, details = run_final_audit(game_dir, "g001", "thief", {})
        assert ok is False
        assert details.get("audit_status") == "NOT_APPLICABLE"

    def test_missing_reveals_returns_failed(self, tmp_path):
        """Commits present but no reveals => FAILED."""
        import json

        from agent.peer_audit import run_final_audit

        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "opponent_commitments.json").write_text(json.dumps({"0": "abc123"}))
        ok, details = run_final_audit(game_dir, "g001", "thief", {})
        assert ok is False
        assert details.get("audit_status") == "FAILED"

    def test_valid_commits_return_passed(self, tmp_path):
        """A verifiable commit/reveal/nonce triple must yield PASSED."""
        import json

        from agent.mcp.crypto import create_commitment
        from agent.peer_audit import run_final_audit

        game_dir = tmp_path / "game"
        game_dir.mkdir()

        h_commit, nonce = create_commitment(
            game_id="g001",
            step=0,
            role="thief",
            state_hash="s" * 64,
            move="SOUTH",
            hint="heading south",
            intent="truth",
        )
        commits = {"0": h_commit}
        reveals = {
            "0": {
                "move": "SOUTH",
                "hint": "heading south",
                "intent": "truth",
                "state_hash": "s" * 64,
            }
        }
        (game_dir / "opponent_commitments.json").write_text(json.dumps(commits))
        (game_dir / "opponent_reveals.json").write_text(json.dumps(reveals))

        ok, details = run_final_audit(game_dir, "g001", "thief", {0: nonce})
        assert ok is True
        assert details.get("audit_status") == "PASSED"


# ---------------------------------------------------------------------------
# 0.4 Exactly six gamelets
# ---------------------------------------------------------------------------


class TestExactlySixGamelets:
    def test_six_gamelets_accepted(self, tmp_path):
        gs = GameSeries(games_dir=tmp_path, n_gamelets=6)
        assert gs.n_gamelets == 6

    def test_five_gamelets_rejected_in_counted_mode(self, tmp_path):
        with pytest.raises(ValueError, match="exactly"):
            GameSeries(games_dir=tmp_path, n_gamelets=5)

    def test_seven_gamelets_rejected_in_counted_mode(self, tmp_path):
        with pytest.raises(ValueError, match="exactly"):
            GameSeries(games_dir=tmp_path, n_gamelets=7)

    def test_zero_gamelets_rejected_in_counted_mode(self, tmp_path):
        with pytest.raises(ValueError, match="exactly"):
            GameSeries(games_dir=tmp_path, n_gamelets=0)

    def test_five_gamelets_allowed_in_uncounted_mode(self, tmp_path):
        gs = GameSeries(games_dir=tmp_path, n_gamelets=5, uncounted=True)
        assert gs.n_gamelets == 5
        assert gs.uncounted is True

    def test_seven_gamelets_allowed_in_uncounted_mode(self, tmp_path):
        gs = GameSeries(games_dir=tmp_path, n_gamelets=7, uncounted=True)
        assert gs.n_gamelets == 7

    @pytest.mark.asyncio
    async def test_uncounted_series_result_flags_uncounted(self, tmp_path):
        gs = GameSeries(games_dir=tmp_path, n_gamelets=2, uncounted=True)

        async def mock_run_game(**kwargs):
            return {"winner": "cop", "audit_ok": True, "final_step": 5}

        with patch.object(gs, "_make_runner") as mock_factory:
            mock_runner = AsyncMock()
            mock_runner.run_game = mock_run_game
            mock_factory.return_value = mock_runner
            result = await gs.run_series(series_id="test_uncounted")

        assert result["counted"] is False


# ---------------------------------------------------------------------------
# 0.5 No LLM movement without bilateral opt-in
# ---------------------------------------------------------------------------


class TestNoLLMMovementFallback:
    @pytest.mark.asyncio
    async def test_select_move_uses_heuristic_not_llm_when_rl_fails(self):
        """When RL fails, select_move must fall back to heuristic, not LLM."""
        from agent.peer_turn_helpers import select_move

        runtime = MagicMock()
        runtime.role = "cop"
        runtime._build_observation.return_value = {}
        runtime._select_move_rl.side_effect = RuntimeError("RL unavailable")

        board_state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "turn": 0,
            "grid_size": 7,
            "barriers": [],
            "move_history": [],
        }

        llm_called = []

        async def spy_llm(*args, **kwargs):
            llm_called.append(True)
            return "NORTH"

        runtime._select_move_llm_async = spy_llm

        move = await select_move(runtime, board_state)

        assert llm_called == [], "LLM must not be called when RL fails"
        assert move in {"NORTH", "SOUTH", "EAST", "WEST", "STAY"}

    @pytest.mark.asyncio
    async def test_select_move_returns_legal_heuristic_move(self):
        """select_move now uses only heuristic (no RL path) to avoid hidden coord leaks."""
        from agent.peer_turn_helpers import select_move

        runtime = MagicMock()
        runtime.role = "thief"

        board_state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "turn": 0,
            "grid_size": 7,
            "barriers": [],
            "move_history": [],
        }
        move = await select_move(runtime, board_state)
        assert move in {"NORTH", "SOUTH", "EAST", "WEST", "STAY"}, (
            "select_move must return a legal heuristic move"
        )
