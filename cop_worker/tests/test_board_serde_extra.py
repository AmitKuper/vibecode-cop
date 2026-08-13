"""Cover board_serde aliases, role lookup, and from_dict guards."""

from __future__ import annotations

import pytest

from cop_worker.board import Board


def _board() -> Board:
    return Board(cop_position=[0, 0], thief_position=[3, 3], turn=2, grid_size=7)


def test_to_state_and_from_state_round_trip():
    board = _board()
    state = board.to_state()
    restored = Board.from_state(state)
    assert restored.cop_position == [0, 0]
    assert restored.thief_position == [3, 3]
    assert restored.turn == 2


def test_from_dict_requires_cop_position():
    with pytest.raises(ValueError, match="cop_position"):
        Board.from_dict({"thief_position": [1, 1]})


def test_from_dict_requires_thief_position():
    with pytest.raises(ValueError, match="thief_position"):
        Board.from_dict({"cop_position": [1, 1]})


def test_get_position_by_role():
    board = _board()
    assert board.get_position("cop") == [0, 0]
    assert board.get_position("thief") == [3, 3]
    with pytest.raises(ValueError, match="Invalid role"):
        board.get_position("spy")


def test_get_legal_moves_returns_candidate_actions():
    board = _board()
    moves = board.get_legal_moves("cop")
    assert "STAY" in moves
    # Cop at the top-left corner cannot go NORTH or WEST.
    assert "NORTH" not in moves and "WEST" not in moves
