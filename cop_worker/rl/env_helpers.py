"""Stateless helper functions for CopThiefEnv.

Extracted from environment.py to keep each file under 150 lines.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from cop_worker.board import Board

if TYPE_CHECKING:
    pass


def random_starts(grid_size: int, barriers: list) -> tuple[list[int], list[int]]:
    """Pick random cop and thief starting positions on a barrier-free grid."""
    barrier_set = set(map(tuple, barriers))
    free = [(x, y) for x in range(grid_size) for y in range(grid_size) if (x, y) not in barrier_set]
    cop = list(random.choice(free))
    thief = list(random.choice([p for p in free if p != tuple(cop)]))
    return cop, thief


def manhattan_dist(board: Board) -> int:
    """Manhattan distance between cop and thief on the given board."""
    cx, cy = board.cop_position
    tx, ty = board.thief_position
    return abs(cx - tx) + abs(cy - ty)


_PLACE_DELTAS: dict[str, tuple[int, int]] = {
    "PLACE_N": (0, -1),
    "PLACE_S": (0, 1),
    "PLACE_E": (1, 0),
    "PLACE_W": (-1, 0),
}


def apply_place_action(board: Board, action: str, grid_size: int, barriers_remaining: int) -> int:
    """Place a barrier ahead of the cop and return updated barriers_remaining count."""
    if barriers_remaining <= 0:
        return barriers_remaining
    dx, dy = _PLACE_DELTAS[action]
    cx, cy = board.cop_position
    bx, by = cx + dx, cy + dy
    if not (0 <= bx < grid_size and 0 <= by < grid_size):
        return barriers_remaining
    # Placing a barrier on the thief's cell is legal capture — do not skip it.
    if board.place_barrier(bx, by):
        return barriers_remaining - 1
    return barriers_remaining
