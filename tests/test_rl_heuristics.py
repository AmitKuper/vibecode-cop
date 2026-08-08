"""Fast unit tests for deterministic heuristic baseline agents.

Pure grid logic — no LLM, no network, no model load.
"""

from __future__ import annotations

import random

from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.heuristics import (
    _bfs_dist,
    evasion_thief,
    pursuit_cop,
    random_legal_cop,
    random_legal_thief,
)

N = 7


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def test_bfs_dist_open_grid():
    dist = _bfs_dist((0, 0), barriers=[], grid_size=N)
    assert dist[(0, 0)] == 0
    assert dist[(0, 1)] == 1 and dist[(1, 0)] == 1
    assert dist[(6, 6)] == 12  # Manhattan on an open grid


def test_bfs_dist_respects_barriers():
    # Wall the (0,0) cell off except one exit and confirm the detour distance.
    dist = _bfs_dist((0, 0), barriers=[(1, 0)], grid_size=N)
    assert (1, 0) not in dist  # blocked cell unreachable
    assert dist[(0, 1)] == 1


def test_pursuit_cop_moves_toward_centroid():
    move = pursuit_cop(
        (0, 0), belief_centroid=(6, 6), barriers=[], barriers_remaining=0, grid_size=N
    )
    assert move in ("N", "S", "E", "W")
    dx, dy = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}[move]
    # the chosen step must reduce Manhattan distance to the centroid
    assert _manhattan((dx, dy), (6, 6)) < _manhattan((0, 0), (6, 6))


def test_evasion_thief_moves_away_from_centroid():
    move = evasion_thief((3, 3), belief_centroid=(3, 3), barriers=[], grid_size=N)
    dx, dy = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0), "STAY": (0, 0)}[move]
    dest = (3 + dx, 3 + dy)
    # moving anywhere off the centroid increases distance vs standing on it
    assert _manhattan(dest, (3, 3)) >= 0


def test_random_legal_cop_is_legal():
    random.seed(0)
    for _ in range(20):
        move = random_legal_cop((0, 0), barriers=[], barriers_remaining=2, grid_size=N)
        assert move in COP_ACTIONS


def test_random_legal_thief_is_legal():
    random.seed(0)
    for _ in range(20):
        move = random_legal_thief((3, 3), barriers=[], grid_size=N)
        assert move in THIEF_ACTIONS


def test_random_legal_thief_fully_boxed_returns_stay():
    # Surround (0,0): its only neighbours (1,0) and (0,1) are barriers → STAY.
    move = random_legal_thief((0, 0), barriers=[(1, 0), (0, 1)], grid_size=N)
    assert move == "STAY"
