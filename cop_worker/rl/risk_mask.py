"""Belief-risk safety mask layered after the canonical legal-action mask."""

from __future__ import annotations

import math

import numpy as np

from cop_worker.observation import BeliefState

_MOVE_DELTAS = {
    "N": (0, -1),
    "S": (0, 1),
    "E": (1, 0),
    "W": (-1, 0),
    "STAY": (0, 0),
}


def _destination(position: tuple[int, int], action: str) -> tuple[int, int]:
    dx, dy = _MOVE_DELTAS.get(action, (0, 0))
    return position[0] + dx, position[1] + dy


def belief_risk_score(
    destination: tuple[int, int],
    belief: BeliefState,
    barriers: list[tuple[int, int]],
) -> float:
    """Expected inverse distance plus local trap risk, using no hidden coordinate."""
    x, y = destination
    probability = np.asarray(belief.prob, dtype=float)
    yy, xx = np.indices(probability.shape)
    expected_proximity = float((probability / (1.0 + np.abs(xx - x) + np.abs(yy - y))).sum())
    blocked = set(barriers)
    exits = sum(
        0 <= x + dx < belief.grid_size
        and 0 <= y + dy < belief.grid_size
        and (x + dx, y + dy) not in blocked
        for dx, dy in _MOVE_DELTAS.values()
        if (dx, dy) != (0, 0)
    )
    trap_risk = (4 - exits) * 0.04
    return expected_proximity + trap_risk


def belief_safe_actions(
    own_position: tuple[int, int],
    belief: BeliefState,
    legal_actions: list[str],
    barriers: list[tuple[int, int]],
    *,
    keep_fraction: float = 0.6,
    min_keep: int = 2,
) -> list[str]:
    """Keep the least risky legal thief actions without ever creating an empty mask."""
    if not legal_actions:
        return []
    keep = min(len(legal_actions), max(min_keep, math.ceil(len(legal_actions) * keep_fraction)))
    ranked = sorted(
        legal_actions,
        key=lambda action: (
            belief_risk_score(_destination(own_position, action), belief, barriers),
            legal_actions.index(action),
        ),
    )
    allowed = set(ranked[:keep])
    return [action for action in legal_actions if action in allowed]
