"""Natural-language hint generation — dependency-neutral utility.

Imported by peer_agent_passive, peer_turn_loop, and any language layer.
Must not import from peer_runtime, peer_agent_passive, or peer_turn_loop.
"""

from __future__ import annotations

import random

_HINT_TEMPLATES: dict[str, list[str]] = {
    "NORTH": ["heading north", "moving toward the top", "going up"],
    "SOUTH": ["heading south", "moving toward the bottom", "going down"],
    "EAST": ["heading east", "moving right", "going east"],
    "WEST": ["heading west", "moving left", "going west"],
    "STAY": ["holding position", "staying put", "not moving"],
}


def generate_hint(move: str, rng: random.Random | None = None) -> str:
    """Return a natural-language hint phrase for the given move direction."""
    _rng = rng or random
    options = _HINT_TEMPLATES.get(move.upper(), [f"moving {move.lower()}"])
    return _rng.choice(options)
