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
    LLM may be injected for high-quality text; templates are the fallback.
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

    def __init__(self, role: str, bluff_probability: float = 0.3, llm_hint_generator=None):
        self.role = role
        self.bluff_probability = bluff_probability
        self._opponent_move_history: list[str] = []
        self._trust_history: list[bool] = []
        self._llm_hint = llm_hint_generator  # LLMHintGenerator | None

    def choose_intent(
        self,
        step: int,
        belief_entropy: float = 1.0,
        *,
        trust_history: list[bool] | None = None,
        gamelet: int = 1,
        physical_action: str = "STAY",
        token_budget: int = 15,
    ) -> DeceptionIntent:
        """
        Choose deception intent based on game context.
        High entropy (uncertain belief) → more likely to lie.
        Low entropy (confident belief) → more likely to truth or bluff.
        """
        if token_budget <= 4:
            return DeceptionIntent.AMBIGUOUS
        history = self._trust_history if trust_history is None else trust_history
        trust = sum(history) / len(history) if history else 0.5
        uncertainty = max(0.0, min(1.0, belief_entropy / 4.0))
        ambiguous_weight = 0.08 + 0.12 * uncertainty
        lie_weight = 0.12 + 0.28 * uncertainty + 0.08 * (1.0 - trust)
        bluff_weight = self.bluff_probability * (0.35 + 0.65 * trust)
        if physical_action.startswith("PLACE_") or physical_action == "STAY":
            bluff_weight += 0.06
        # Vary the controlled policy across a six-gamelet series without coupling it to movement.
        if (step + gamelet) % 5 == 0:
            ambiguous_weight += 0.05
        r = random.random()
        if r < ambiguous_weight:
            return DeceptionIntent.AMBIGUOUS
        if r < ambiguous_weight + lie_weight:
            return DeceptionIntent.LIE
        if r < ambiguous_weight + lie_weight + bluff_weight:
            return DeceptionIntent.BLUFF
        return DeceptionIntent.TRUTH

    def generate(self, move: str, intent: DeceptionIntent) -> str:
        """Generate a free-language hint, preferring LLM text over templates."""
        if self._llm_hint is not None:
            try:
                text = self._llm_hint.generate(move, intent.value)
                if text:
                    return text
            except Exception:
                pass  # fall through to templates
        return self._template(move, intent)

    def _template(self, move: str, intent: DeceptionIntent) -> str:
        """Template fallback — always works, zero latency."""
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

    def record_opponent_hint(self, hint: str, trustworthy: bool | None = None) -> None:
        """Track opponent hints for behavioral profiling."""
        self._opponent_move_history.append(hint)
        if trustworthy is not None:
            self._trust_history.append(bool(trustworthy))

    def opponent_hint_count(self) -> int:
        return len(self._opponent_move_history)

    def hint_is_numeric_location(self, hint: str) -> bool:
        """Return True if hint contains suspicious numeric coordinates."""
        return bool(re.search(r"\b\d+\s*,\s*\d+\b|\b(row|col|position)\s+\d+", hint, re.I))
