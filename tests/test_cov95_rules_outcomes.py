"""Cover the outcome-determination branches of cop_worker.rules_outcomes."""

from __future__ import annotations

from cop_worker.board import Board
from cop_worker.rules_outcomes import GameOutcome, check_game_status


def test_capture_is_cop_win():
    board = Board(cop_position=[3, 3], thief_position=[3, 3], turn=2)
    assert check_game_status(board, max_turns=35) is GameOutcome.COP_WIN


def test_max_turns_is_thief_win():
    board = Board(cop_position=[0, 0], thief_position=[6, 6], turn=35)
    assert check_game_status(board, max_turns=35) is GameOutcome.THIEF_WIN


def test_trapped_thief_is_cop_win():
    # Thief cornered at (0,0); barriers seal both orthogonal exits so no escape.
    board = Board(
        cop_position=[5, 5],
        thief_position=[0, 0],
        turn=1,
        barriers=[[1, 0], [0, 1]],
    )
    assert not board.has_orthogonal_escape("thief")
    assert check_game_status(board, max_turns=35) is GameOutcome.COP_WIN


def test_ongoing_game():
    board = Board(cop_position=[0, 0], thief_position=[6, 6], turn=1)
    assert check_game_status(board, max_turns=35) is GameOutcome.ONGOING
