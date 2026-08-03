"""Deterministic heuristic baseline agents for ablation studies."""

from __future__ import annotations

import random
from collections import deque

from agent.rl.action_space import COP_ACTIONS, MOVE_DELTAS, THIEF_ACTIONS


def _bfs_dist(
    start: tuple[int, int],
    barriers: list[tuple[int, int]],
    grid_size: int,
) -> dict[tuple[int, int], int]:
    """BFS distance from start; returns {pos: dist}."""
    barrier_set = set(map(tuple, barriers))
    visited: dict[tuple[int, int], int] = {tuple(start): 0}
    q: deque[tuple[int, int]] = deque([tuple(start)])
    while q:
        r, c = q.popleft()
        d = visited[(r, c)]
        for dr, dc in [(-1, 0), (1, 0), (0, 1), (0, -1)]:
            nr, nc = r + dr, c + dc
            if (
                0 <= nr < grid_size
                and 0 <= nc < grid_size
                and (nr, nc) not in barrier_set
                and (nr, nc) not in visited
            ):
                visited[(nr, nc)] = d + 1
                q.append((nr, nc))
    return visited


def random_legal_cop(
    position: tuple[int, int],
    barriers: list[tuple[int, int]],
    barriers_remaining: int,
    grid_size: int,
) -> str:
    """Return a random legal cop action."""
    from agent.rl.action_space import compute_legal_mask_cop

    mask = compute_legal_mask_cop(position, barriers, barriers_remaining, grid_size)
    legal = [COP_ACTIONS[i] for i in range(len(COP_ACTIONS)) if mask[i]]
    return random.choice(legal) if legal else "STAY"


def random_legal_thief(
    position: tuple[int, int],
    barriers: list[tuple[int, int]],
    grid_size: int,
) -> str:
    """Return a random legal thief action."""
    from agent.rl.action_space import compute_legal_mask_thief

    mask = compute_legal_mask_thief(position, barriers, grid_size)
    legal = [THIEF_ACTIONS[i] for i in range(len(THIEF_ACTIONS)) if mask[i]]
    return random.choice(legal) if legal else "STAY"


def pursuit_cop(
    cop_pos: tuple[int, int],
    belief_centroid: tuple[int, int],
    barriers: list[tuple[int, int]],
    barriers_remaining: int,
    grid_size: int,
) -> str:
    """Move toward highest-belief cell (greedy Manhattan)."""
    best_move = "STAY"
    best_dist = float("inf")
    barrier_set = set(map(tuple, barriers))
    r, c = cop_pos
    tr, tc = belief_centroid
    for action in ["N", "S", "E", "W", "STAY"]:
        dr, dc = MOVE_DELTAS[action]
        nr, nc = r + dr, c + dc
        if 0 <= nr < grid_size and 0 <= nc < grid_size and (nr, nc) not in barrier_set:
            d = abs(nr - tr) + abs(nc - tc)
            if d < best_dist:
                best_dist = d
                best_move = action
    return best_move


def evasion_thief(
    thief_pos: tuple[int, int],
    belief_centroid: tuple[int, int],
    barriers: list[tuple[int, int]],
    grid_size: int,
) -> str:
    """Move away from belief centroid (greedy Manhattan)."""
    best_move = "STAY"
    best_dist = -1
    barrier_set = set(map(tuple, barriers))
    r, c = thief_pos
    tr, tc = belief_centroid
    for action in ["N", "S", "E", "W", "STAY"]:
        dr, dc = MOVE_DELTAS[action]
        nr, nc = r + dr, c + dc
        if 0 <= nr < grid_size and 0 <= nc < grid_size and (nr, nc) not in barrier_set:
            d = abs(nr - tr) + abs(nc - tc)
            if d >= best_dist:
                best_dist = d
                best_move = action
    return best_move
