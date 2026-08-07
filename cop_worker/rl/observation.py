"""Asymmetric observation builders for cop and thief RL agents.

Cop observation shape depends on whether barriers are enabled:
  - 4 channels when cop_barrier_quota == 0 (legacy / no barrier mode)
  - 5 channels when cop_barrier_quota  > 0 (barrier placement mode)

All grids are shape (C, grid_size, grid_size), nested Python lists [y][x].

Channel layout
--------------
Cop observation (4 or 5 channels):
    0  cop position        1-hot
    1  barriers            1 where blocked, 0 elsewhere
    2  scent field         float 0.0–0.9 centred on thief (Chebyshev decay)
    3  turns remaining     scalar broadcast, normalized 0–1
    4  barriers remaining  scalar broadcast, normalized 0–1 (only when quota > 0)

Thief observation (4 channels):
    0  thief position      1-hot
    1  cop scent field     historical trail (not live cop position)
    2  barriers            1 where blocked, 0 elsewhere
    3  turns remaining     scalar broadcast, normalized 0–1
"""

from __future__ import annotations

from cop_worker.board import Board
from cop_worker.rules_engine import RulesEngine


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


def cop_observation(
    board: Board,
    rules: RulesEngine,
    max_steps: int,
    barriers_remaining: int = 0,
    barrier_quota: int = 0,
) -> list[list[list[float]]]:
    """Build cop observation (4 channels normally, 5 when barrier_quota > 0).

    Args:
        board:             Current board state.
        rules:             RulesEngine instance (provides scent computation).
        max_steps:         Total step budget (for normalizing turns_remaining).
        barriers_remaining: How many barriers the cop can still place.
        barrier_quota:     Total barriers allocated for this game (0 = disabled).

    Returns:
        List of 4 or 5 channels, each a grid_size×grid_size float grid.
          0  cop position        1-hot
          1  barriers            1 where blocked, 0 elsewhere
          2  thief scent field   accumulated/decayed historical thief trail (not live GPS)
          3  turns remaining     scalar broadcast, normalized 0–1
          4  barriers remaining  scalar broadcast, normalized 0–1 (only when quota > 0)
    """
    n = board.grid_size
    cx, cy = board.cop_position
    channels = [
        _one_hot(n, cx, cy),
        _barrier_grid(board),
        rules.get_scent_field(),  # accumulated/decayed historical thief trail, not live GPS
        _turns_remaining_grid(board, max_steps),
    ]
    if barrier_quota > 0:
        channels.append(_barrier_quota_grid(n, barriers_remaining, barrier_quota))
    return channels


def local_thief_observation(
    board: Board,
    max_steps: int,
    cop_scent_field: list[list[float]] | None = None,
) -> list[list[list[float]]]:
    """Build 4-channel observation for the thief agent. Preferred name.

    The thief does NOT know the cop's current (live) position. Instead it
    observes a cop scent field — a historical trail of where the cop has been.

    Args:
        board: Current board state.
        max_steps: Total step budget (for normalizing turns_remaining).
        cop_scent_field: NxN float grid representing cop historical trail.
            None → all zeros (thief has no scent information yet).

    Returns:
        List of 4 channels, each a grid_size×grid_size float grid.
          0  thief position       1-hot
          1  cop scent field      historical trail (not live cop position)
          2  barriers             1 where blocked
          3  turns remaining      scalar broadcast, normalized 0–1
    """
    n = board.grid_size
    tx, ty = board.thief_position
    scent_ch = _empty_grid(n) if cop_scent_field is None else cop_scent_field
    return [
        _one_hot(n, tx, ty),
        scent_ch,
        _barrier_grid(board),
        _turns_remaining_grid(board, max_steps),
    ]


def thief_observation(
    board: Board,
    max_steps: int,
    cop_scent_field: list[list[float]] | None = None,
) -> list[list[list[float]]]:
    """Build 4-channel observation for the thief agent. Alias for local_thief_observation().

    Args:
        board: Current board state.
        max_steps: Total step budget (for normalizing turns_remaining).
        cop_scent_field: NxN float grid representing cop historical trail.
            None → all zeros. Channel 1 is cop scent field (historical trail, not live position).

    Returns:
        List of 4 channels, each a grid_size×grid_size float grid.
          0  thief position       1-hot
          1  cop scent field      historical trail (not live cop position)
          2  barriers             1 where blocked
          3  turns remaining      scalar broadcast, normalized 0–1
    """
    return local_thief_observation(board, max_steps, cop_scent_field=cop_scent_field)


def observation_shape(
    grid_size: int, role: str = "thief", barrier_quota: int = 0
) -> tuple[int, int, int]:  # noqa: E501
    """Return (channels, height, width) — useful when building network input layers."""
    n_channels = (5 if barrier_quota > 0 else 4) if role == "cop" else 4
    return (n_channels, grid_size, grid_size)
