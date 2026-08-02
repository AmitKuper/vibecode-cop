"""Helpers for CrewMixin — RL policy cache, move parsing, observation building."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_VALID_MOVES = {"N", "S", "E", "W", "STAY"}
_LONG_TO_SHORT = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "STAY": "STAY"}

_rl_policies: dict = {}


def get_rl_policy(role: str):
    """Load and cache the best RL policy for *role*. Returns None if unavailable."""
    if role in _rl_policies:
        return _rl_policies[role]
    try:
        from agent.rl.policy import RLPolicy

        policy = RLPolicy.load(role, models_dir=Path("models"))
        _rl_policies[role] = policy
        logger.info(f"[CrewMixin] Loaded RL policy for {role}")
        return policy
    except Exception as exc:
        logger.warning(f"[CrewMixin] RL policy unavailable for {role}: {exc}")
        _rl_policies[role] = None
        return None


def parse_move(raw: str, candidates: list[str]) -> str:
    """Extract a valid move token from LLM raw output.

    Tries exact match first, then scans for a token in candidates.
    Raises ValueError if no valid move can be found.
    """
    text = raw.strip().upper()
    for long, short in _LONG_TO_SHORT.items():
        text = re.sub(rf"\b{long}\b", short, text)
    if text in _VALID_MOVES:
        return text
    for token in candidates:
        if re.search(rf"\b{token}\b", text):
            return token
    raise ValueError(f"No valid move in LLM output: {raw!r}. Candidates: {candidates}")


def build_observation(role: str, game_state: dict) -> dict:
    """Build role-filtered observation dict from game state.

    Hidden-info compliance: each role receives only its own position plus
    indirect signals. True opponent coordinates are never included.
    """
    cop_pos = game_state.get("cop_position", [0, 0])
    thief_pos = game_state.get("thief_position", [3, 3])
    turn = game_state.get("turn", 0)
    grid_size = 6  # max index on a 7×7 grid

    if role == "cop":
        own_pos = cop_pos
        role_state = {
            "own_position": own_pos,
            "scent_field": game_state.get("scent_field", []),
            "turn": turn,
        }
    else:
        own_pos = thief_pos
        role_state = {
            "own_position": own_pos,
            "last_revealed_cop_pos": game_state.get("last_revealed_cop_pos"),
            "turn": turn,
        }

    x, y = own_pos
    candidates = []
    if x > 0:
        candidates.append("W")
    if x < grid_size:
        candidates.append("E")
    if y > 0:
        candidates.append("N")
    if y < grid_size:
        candidates.append("S")
    candidates.append("STAY")

    return {**role_state, "candidate_actions": candidates, "grid_state": role_state}
