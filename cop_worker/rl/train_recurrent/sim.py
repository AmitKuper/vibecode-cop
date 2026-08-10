"""Domain-state helpers shared by episode rollout, opponents, and rewards."""

from __future__ import annotations

import random

from cop_worker.domain.transition import apply_joint_action
from cop_worker.domain.types import DomainState
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS


def _initial_state(
    rng: random.Random, random_start: bool = True, grid_size: int = 7
) -> DomainState:
    if random_start:
        cop = (rng.randrange(grid_size), rng.randrange(grid_size))
        thief = (rng.randrange(grid_size), rng.randrange(grid_size))
        while thief == cop:
            thief = (rng.randrange(grid_size), rng.randrange(grid_size))
    else:
        cop, thief = (0, 0), (3, 3)
    return DomainState(
        turn=0,
        grid_size=grid_size,
        cop_position=cop,
        thief_position=thief,
        barriers=[],
        cop_barriers_remaining=14,
        move_history=[],
        scent_grid=[[0.0] * grid_size for _ in range(grid_size)],
    )


def _legal(state: DomainState, role: str) -> list[str]:
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    results = (
        apply_joint_action(state, action, "STAY")
        if role == "cop"
        else apply_joint_action(state, "STAY", action)
        for action in actions
    )
    return [
        action
        for action, result in zip(actions, results, strict=True)
        if (result.cop_action_legal if role == "cop" else result.thief_action_legal)
    ]


def _distance(state: DomainState) -> int:
    return abs(state.cop_position[0] - state.thief_position[0]) + abs(
        state.cop_position[1] - state.thief_position[1]
    )


def _action_position(position: tuple[int, int], action: str) -> tuple[int, int]:
    delta = {
        "N": (0, -1),
        "S": (0, 1),
        "E": (1, 0),
        "W": (-1, 0),
        "STAY": (0, 0),
    }.get(action, (0, 0))
    return position[0] + delta[0], position[1] + delta[1]


def _local_exit_count(
    position: tuple[int, int], barriers: list[tuple[int, int]], grid_size: int
) -> int:
    blocked = set(barriers)
    return sum(
        0 <= position[0] + dx < grid_size
        and 0 <= position[1] + dy < grid_size
        and (position[0] + dx, position[1] + dy) not in blocked
        for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0))
    )


def _belief_trap_reward(
    opponent_belief,
    before_barriers: list[tuple[int, int]],
    after_barriers: list[tuple[int, int]],
    grid_size: int,
) -> float:
    """Reward belief-supported trap construction without consulting hidden coordinates."""
    placed = set(after_barriers) - set(before_barriers)
    if not placed:
        return 0.0
    trap_gain = 0.0
    proximity_mass = 0.0
    probability = opponent_belief.prob
    for y in range(grid_size):
        for x in range(grid_size):
            mass = float(probability[y, x])
            if mass <= 0.0:
                continue
            cell = (x, y)
            before_exits = _local_exit_count(cell, before_barriers, grid_size)
            after_exits = _local_exit_count(cell, after_barriers, grid_size)
            trap_gain += mass * max(0, before_exits - after_exits)
            if any(abs(x - bx) + abs(y - by) <= 1 for bx, by in placed):
                proximity_mass += mass
    return min(0.45, 0.25 * trap_gain + 0.20 * proximity_mass)
