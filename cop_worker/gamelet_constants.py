"""Gamelet action vocabulary, coordinate deltas, and grid constants."""

from __future__ import annotations


class GameletError(Exception):
    """General gamelet error."""


# Cop can move in cardinal directions or place a barrier, or stay
_COP_ACTIONS = ["N", "S", "E", "W", "stay", "barrier_N", "barrier_S", "barrier_E", "barrier_W"]

# Board coordinate deltas keyed by gamelet direction string (matches Board.DIRECTIONS
# and RLMover.apply: N = y-1, S = y+1, E = x+1, W = x-1).
_MOVE_DELTAS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0), "stay": (0, 0)}

# Mapping from policy uppercase names to gamelet action dict format
_POLICY_TO_GAMELET_COP = {
    "N": "N",
    "S": "S",
    "E": "E",
    "W": "W",
    "STAY": "stay",
    "PLACE_N": "barrier_N",
    "PLACE_S": "barrier_S",
    "PLACE_E": "barrier_E",
    "PLACE_W": "barrier_W",
}

_GRID_SIZE = 7  # canonical grid size matching manifest
