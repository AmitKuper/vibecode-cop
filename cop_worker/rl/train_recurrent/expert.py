"""Local-only belief expert used as teacher and as several opponent families."""

from __future__ import annotations

import numpy as np

from cop_worker.belief_engine import BeliefEngine


def _belief_expert_action(
    own_position: tuple[int, int],
    role: str,
    belief: BeliefEngine,
    legal_actions: list[str],
) -> str:
    """Local-only pursuit/evasion teacher used to prevent policy collapse."""
    target_y, target_x = np.unravel_index(belief.belief.prob.argmax(), belief.belief.prob.shape)
    move_deltas = {
        "N": (0, -1),
        "S": (0, 1),
        "E": (1, 0),
        "W": (-1, 0),
        "STAY": (0, 0),
    }
    place_deltas = {
        "PLACE_N": (0, -1),
        "PLACE_S": (0, 1),
        "PLACE_E": (1, 0),
        "PLACE_W": (-1, 0),
    }
    scored = []
    for action in legal_actions:
        dx, dy = move_deltas.get(action, (0, 0))
        own = (own_position[0] + dx, own_position[1] + dy)
        distance = abs(own[0] - target_x) + abs(own[1] - target_y)
        score = -distance if role == "cop" else distance
        if role == "cop" and action in place_deltas:
            pdx, pdy = place_deltas[action]
            placement = (own_position[0] + pdx, own_position[1] + pdy)
            score += 20 if placement == (target_x, target_y) else -0.25
        if action == "STAY":
            score -= 0.05
        scored.append((score, -legal_actions.index(action), action))
    return max(scored)[2]
