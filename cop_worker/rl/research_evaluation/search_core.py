"""Depth-limited determinized value search primitives."""

from __future__ import annotations

import math

from cop_worker.domain.transition import apply_joint_action
from cop_worker.domain.types import DomainState
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)


def _hypothetical_state(
    state: DomainState, role: str, opponent_position: tuple[int, int]
) -> DomainState:
    field = "thief_position" if role == "cop" else "cop_position"
    return state.model_copy(update={field: opponent_position})


def _leaf_value(state: DomainState, role: str) -> float:
    """Bounded perfect-information leaf value used only inside belief particles."""
    distance = abs(state.cop_position[0] - state.thief_position[0]) + abs(
        state.cop_position[1] - state.thief_position[1]
    )
    barriers = set(state.barriers)
    tx, ty = state.thief_position
    exits = sum(
        0 <= tx + dx < state.grid_size
        and 0 <= ty + dy < state.grid_size
        and (tx + dx, ty + dy) not in barriers
        for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0))
    )
    time_fraction = state.turn / 35.0
    cop_value = (
        -0.30 * distance
        + 0.55 * (4 - exits)
        + 0.08 * state.cop_barriers_remaining
        - 0.80 * time_fraction
    )
    return cop_value if role == "cop" else -cop_value


def _terminal_value(outcome: str, role: str, turn: int) -> float:
    if outcome == "ongoing":
        raise ValueError("terminal value requested for ongoing state")
    winner = "cop" if outcome == "cop_win" else "thief"
    speed = (35 - min(turn, 35)) / 35.0
    return (12.0 + speed) if winner == role else (-12.0 - speed)


def _fast_legal(state: DomainState, role: str) -> list[str]:
    """Equivalent local legality calculation for inner search nodes."""
    barriers = [tuple(item) for item in state.barriers]
    if role == "cop":
        actions = COP_ACTIONS
        mask = compute_legal_mask_cop(
            state.cop_position,
            barriers,
            state.cop_barriers_remaining,
            state.grid_size,
        )
    else:
        actions = THIEF_ACTIONS
        mask = compute_legal_mask_thief(state.thief_position, barriers, state.grid_size)
    return [action for action, allowed in zip(actions, mask, strict=True) if allowed]


def _determinized_value(state: DomainState, role: str, depth: int) -> float:
    """Small simultaneous expectiminimax search inside one belief particle."""
    if depth <= 0:
        return _leaf_value(state, role)
    own_actions = _fast_legal(state, role)
    opponent_role = "thief" if role == "cop" else "cop"
    opponent_actions = _fast_legal(state, opponent_role)
    best = -math.inf
    for own in own_actions:
        worst = math.inf
        for opponent in opponent_actions:
            cop_action, thief_action = (own, opponent) if role == "cop" else (opponent, own)
            result = apply_joint_action(state, cop_action, thief_action)
            outcome = result.outcome.value
            value = (
                _terminal_value(outcome, role, result.new_state.turn)
                if outcome != "ongoing"
                else _determinized_value(result.new_state, role, depth - 1)
            )
            worst = min(worst, value)
        best = max(best, worst)
    return best
