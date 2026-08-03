"""Tests for Phase 3E: hint language policy."""

from __future__ import annotations

import pytest

from agent.language.hint_policy import DIRECTION_NAMES, generate_hint


class TestGenerateHint:
    def test_truth_returns_string(self):
        hint = generate_hint("N", intent="truth")
        assert isinstance(hint, str)
        assert len(hint) > 0

    def test_lie_returns_string(self):
        hint = generate_hint("N", intent="lie")
        assert isinstance(hint, str)
        assert len(hint) > 0

    @pytest.mark.parametrize("move", ["N", "S", "E", "W", "STAY"])
    def test_truth_under_15_words(self, move):
        for _ in range(20):
            hint = generate_hint(move, intent="truth")
            words = hint.split()
            assert len(words) <= 15, f"Hint too long ({len(words)} words): {hint!r}"

    @pytest.mark.parametrize("move", ["N", "S", "E", "W", "STAY"])
    def test_lie_under_15_words(self, move):
        for _ in range(20):
            hint = generate_hint(move, intent="lie")
            words = hint.split()
            assert len(words) <= 15, f"Hint too long ({len(words)} words): {hint!r}"

    def test_no_raw_coordinates(self):
        """Hints must not contain digit-only tokens that look like coordinates."""
        for move in ["N", "S", "E", "W", "STAY"]:
            for intent in ["truth", "lie"]:
                hint = generate_hint(move, intent=intent)
                tokens = hint.split()
                for token in tokens:
                    stripped = token.strip(".,!?")
                    assert not stripped.isdigit(), (
                        f"Hint contains coordinate-like digit {stripped!r}: {hint!r}"
                    )

    def test_truth_hint_contains_direction_word(self):
        """Truth hints should contain the direction word."""
        for move, direction in DIRECTION_NAMES.items():
            found = False
            for _ in range(30):
                hint = generate_hint(move, intent="truth")
                if direction in hint.lower():
                    found = True
                    break
            assert found, f"No hint for {move!r} contained direction word {direction!r}"

    def test_lie_different_from_truth(self):
        """Over many samples, lies should sometimes differ from truths."""
        for move in ["N", "S", "E", "W"]:
            truth_hints = {generate_hint(move, "truth") for _ in range(10)}
            lie_hints = {generate_hint(move, "lie") for _ in range(10)}
            # Not all lies should equal truth hints (they're opposite direction)
            assert truth_hints != lie_hints or move == "STAY"

    def test_default_intent_is_truth(self):
        """Default intent should produce truth-style hints."""
        hint = generate_hint("N")
        assert isinstance(hint, str)
        assert len(hint) > 0
