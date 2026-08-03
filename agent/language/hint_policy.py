"""Language policy for free-language hint generation.

Template-based only — no LLM calls. Keeps hints role-safe (no coordinates).
"""

from __future__ import annotations

import random

TRUTHFUL_TEMPLATES = [
    "I am heading {direction}.",
    "Moving toward {direction}.",
    "Going {direction} this turn.",
]
LIE_TEMPLATES = [
    "I am heading {opposite}.",
    "Moving {opposite}.",
    "I think {opposite} looks promising.",
]
DIRECTION_NAMES = {
    "N": "north",
    "S": "south",
    "E": "east",
    "W": "west",
    "STAY": "to stay put",
}
OPPOSITES = {
    "N": "south",
    "S": "north",
    "E": "west",
    "W": "east",
    "STAY": "away",
}


def generate_hint(move: str, intent: str = "truth") -> str:
    """Generate a free-language hint. intent='truth'|'lie'."""
    direction = DIRECTION_NAMES.get(move, move.lower())
    if intent == "truth":
        template = random.choice(TRUTHFUL_TEMPLATES)
        return template.format(direction=direction)
    else:
        opposite = OPPOSITES.get(move, direction)
        template = random.choice(LIE_TEMPLATES)
        return template.format(opposite=opposite)
