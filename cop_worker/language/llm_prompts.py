"""Hint prompt templates and builder shared by the LLM backends."""

from __future__ import annotations

_SYSTEM_PROMPT = (
    "You are a player in a grid-based cop-and-thief game. "
    "Reply with ONE short sentence (max 10 words) hinting at your movement direction. "
    "No coordinates, no numbers, no punctuation beyond one period."
)

_INTENT_INSTRUCTION = {
    "truth": "Tell the truth about your direction.",
    "lie": "Lie — describe the opposite direction.",
    "ambiguous": "Be vague — do not reveal your direction.",
    "bluff": "Sound confident but be misleading.",
}

_DIRECTION_NAMES = {
    "N": "north",
    "S": "south",
    "E": "east",
    "W": "west",
    "STAY": "staying put",
}
_OPPOSITES = {
    "N": "south",
    "S": "north",
    "E": "west",
    "W": "east",
    "STAY": "away from here",
}


def _build_user_prompt(move: str, intent: str) -> str:
    direction = _DIRECTION_NAMES.get(move.upper(), move.lower())
    opposite = _OPPOSITES.get(move.upper(), direction)
    instruction = _INTENT_INSTRUCTION.get(intent, _INTENT_INSTRUCTION["truth"])
    return (
        f"You are moving {direction} (opposite would be {opposite}). "
        f"{instruction} One sentence only."
    )
