"""Channel-grid primitives for the RL observation builders.

Split out of ``cop_worker.rl.observation`` (which re-imports every helper, so
``observation._one_hot`` etc. remain available); pure list-of-lists math only.
"""

from __future__ import annotations

from cop_worker.board import Board


def _empty_grid(n: int) -> list[list[float]]:
    return [[0.0] * n for _ in range(n)]


def _one_hot(n: int, x: int, y: int) -> list[list[float]]:
    grid = _empty_grid(n)
    if 0 <= x < n and 0 <= y < n:
        grid[y][x] = 1.0
    return grid


def _barrier_grid(board: Board) -> list[list[float]]:
    n = board.grid_size
    grid = _empty_grid(n)
    for bx, by in board.barriers:
        if 0 <= bx < n and 0 <= by < n:
            grid[by][bx] = 1.0
    return grid


def _turns_remaining_grid(board: Board, max_steps: int) -> list[list[float]]:
    n = board.grid_size
    remaining = max(0, max_steps - board.turn)
    value = remaining / max_steps if max_steps > 0 else 0.0
    return [[value] * n for _ in range(n)]


def _barrier_quota_grid(n: int, remaining: int, quota: int) -> list[list[float]]:
    value = remaining / quota if quota > 0 else 0.0
    return [[value] * n for _ in range(n)]
