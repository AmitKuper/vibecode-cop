"""Board geometry and action vocabulary for the domain transition.

Split out of transition.py so the transition module stays within the project's
150-line rule. These are pure lookups and predicates with no game state; the
transition function remains the single source of truth for the physics itself.
"""

from __future__ import annotations

# Orthogonal deltas (STAY excluded — STAY(0,0) does not change position)
_MOVE_DELTAS: dict[str, tuple[int, int]] = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "EAST": (1, 0),
    "WEST": (-1, 0),
    "STAY": (0, 0),
}

# Short-form aliases accepted from peer messages
_ALIASES: dict[str, str] = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}

# PLACE_* actions for cop barrier placement
_PLACE_DELTAS: dict[str, tuple[int, int]] = {
    "PLACE_N": (0, -1),
    "PLACE_S": (0, 1),
    "PLACE_E": (1, 0),
    "PLACE_W": (-1, 0),
}


def _normalize(action: str) -> str:
    return _ALIASES.get(action.upper(), action.upper())


def _is_valid(x: int, y: int, g: int, barriers: list[tuple[int, int]]) -> bool:
    return 0 <= x < g and 0 <= y < g and (x, y) not in barriers


def _has_orthogonal_escape(pos: tuple[int, int], g: int, barriers: list[tuple[int, int]]) -> bool:
    x, y = pos
    for dx, dy in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
        if _is_valid(x + dx, y + dy, g, barriers):
            return True
    return False
