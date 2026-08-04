"""Language/deception policy — separate from physical movement control."""

from __future__ import annotations

import random
import re
from enum import Enum


class DeceptionIntent(Enum):
    TRUTH = "truth"
    AMBIGUOUS = "ambiguous"
    LIE = "lie"
    BLUFF = "bluff"


class NaturalLanguagePolicy:
    """
    Generates free-language hints independent of physical movement.
    Movement is controlled by RL/heuristic — this only controls language.
    LLM may be injected for high-quality text but defaults to templates.
    """

    TRUTH_TEMPLATES = {
        "N": ["Heading north.", "Moving up.", "Going north this turn."],
        "S": ["Heading south.", "Moving down.", "Going south."],
        "E": ["Moving east.", "Going right.", "Heading east."],
        "W": ["Moving west.", "Going left.", "Heading west."],
        "STAY": ["Staying put.", "Not moving this turn.", "Holding position."],
    }
    LIE_TEMPLATES = {
        "N": ["Moving south.", "Going down.", "Heading south."],
        "S": ["Moving north.", "Going up.", "Heading north."],
        "E": ["Moving west.", "Going left.", "Heading west."],
        "W": ["Moving east.", "Going right.", "Heading east."],
        "STAY": ["Moving quickly.", "On the move.", "Changing position."],
    }
    AMBIGUOUS_TEMPLATES = [
        "Considering my options.",
        "Making a strategic move.",
        "Repositioning.",
        "Adapting to the situation.",
    ]

    def __init__(self, role: str, bluff_probability: float = 0.3):
        self.role = role
        self.bluff_probability = bluff_probability
        self._opponent_move_history: list[str] = []

    def choose_intent(self, step: int, belief_entropy: float = 1.0) -> DeceptionIntent:
        """
        Choose deception intent based on game context.
        High entropy (uncertain belief) → more likely to lie.
        Low entropy (confident belief) → more likely to truth or bluff.
        """
        r = random.random()
        adjusted_bluff = self.bluff_probability * (1.0 + belief_entropy)
        adjusted_bluff = min(0.6, adjusted_bluff)
        if r < 0.1:
            return DeceptionIntent.AMBIGUOUS
        elif r < adjusted_bluff:
            return DeceptionIntent.LIE
        elif r < adjusted_bluff + 0.2:
            return DeceptionIntent.BLUFF
        else:
            return DeceptionIntent.TRUTH

    def generate(self, move: str, intent: DeceptionIntent) -> str:
        """Generate a free-language hint. Never numeric-location protocol."""
        if intent == DeceptionIntent.TRUTH:
            templates = self.TRUTH_TEMPLATES.get(move, ["Moving strategically."])
            return random.choice(templates)
        elif intent == DeceptionIntent.LIE:
            templates = self.LIE_TEMPLATES.get(move, ["Going the other way."])
            return random.choice(templates)
        elif intent == DeceptionIntent.AMBIGUOUS:
            return random.choice(self.AMBIGUOUS_TEMPLATES)
        else:  # BLUFF — mix truth and misdirection
            if random.random() < 0.5:
                templates = self.TRUTH_TEMPLATES.get(move, ["Moving strategically."])
            else:
                templates = self.AMBIGUOUS_TEMPLATES
            return random.choice(templates)

    def record_opponent_hint(self, hint: str) -> None:
        """Track opponent hints for behavioral profiling."""
        self._opponent_move_history.append(hint)

    def opponent_hint_count(self) -> int:
        return len(self._opponent_move_history)

    def hint_is_numeric_location(self, hint: str) -> bool:
        """Return True if hint contains suspicious numeric coordinates."""
        return bool(re.search(r"\b\d+\s*,\s*\d+\b|\b(row|col|position)\s+\d+", hint, re.I))
