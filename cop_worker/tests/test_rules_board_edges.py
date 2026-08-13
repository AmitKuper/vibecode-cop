"""Cover edge/rejection branches in Board.apply_move and RulesEngine.apply_moves."""

from __future__ import annotations

from cop_worker.board import Board
from cop_worker.rules_engine import RulesEngine


def _board() -> Board:
    return Board(cop_position=[3, 3], thief_position=[5, 5], turn=0, grid_size=7)


def test_apply_move_rejects_unknown_action():
    board = _board()
    assert board.apply_move("cop", "TELEPORT") is False


def test_apply_move_rejects_unknown_role():
    board = _board()
    assert board.apply_move("referee", "NORTH") is False


def test_apply_move_rejects_out_of_bounds():
    board = Board(cop_position=[0, 0], thief_position=[5, 5], grid_size=7)
    # NORTH from the top row leaves the grid.
    assert board.apply_move("cop", "NORTH") is False
    assert board.cop_position == [0, 0]


def test_apply_move_moves_thief():
    board = _board()
    assert board.apply_move("thief", "WEST") is True
    assert board.thief_position == [4, 5]


def test_place_barrier_rejects_out_of_bounds_and_duplicate():
    board = _board()
    assert board.place_barrier(99, 99) is False
    assert board.place_barrier(2, 2) is True
    assert board.place_barrier(2, 2) is False  # already present


def test_validate_move_rejects_unknown_action():
    rules = RulesEngine(_board())
    assert rules.validate_move("cop", "FLY") is False


def test_apply_moves_rejects_illegal_cop_and_thief():
    rules = RulesEngine(Board(cop_position=[0, 0], thief_position=[6, 6], grid_size=7))
    # Cop at corner cannot go NORTH.
    assert rules.apply_moves("NORTH", "STAY") is False
    # Thief at far corner cannot go SOUTH.
    assert rules.apply_moves("STAY", "SOUTH") is False


def test_apply_moves_accepts_legal_moves_and_advances_turn():
    rules = RulesEngine(_board())
    assert rules.apply_moves("EAST", "WEST") is True
    assert rules.board.turn == 1
    assert len(rules.board.move_history) == 1
