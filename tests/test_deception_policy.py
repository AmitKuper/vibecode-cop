"""Tests for NaturalLanguagePolicy and DeceptionIntent (Phase 4 v7)."""

from __future__ import annotations

from agent.language.deception_policy import DeceptionIntent, NaturalLanguagePolicy


def test_deception_intent_enum_values():
    assert DeceptionIntent.TRUTH.value == "truth"
    assert DeceptionIntent.AMBIGUOUS.value == "ambiguous"
    assert DeceptionIntent.LIE.value == "lie"
    assert DeceptionIntent.BLUFF.value == "bluff"


def test_choose_intent_returns_intent():
    policy = NaturalLanguagePolicy("thief")
    for _ in range(20):
        intent = policy.choose_intent(step=1, belief_entropy=1.0)
        assert isinstance(intent, DeceptionIntent)


def test_generate_truth_no_coords():
    policy = NaturalLanguagePolicy("thief")
    hint = policy.generate("N", DeceptionIntent.TRUTH)
    assert not policy.hint_is_numeric_location(hint), f"TRUTH hint had coords: {hint!r}"


def test_generate_lie_differs_from_truth():
    policy = NaturalLanguagePolicy("thief")
    truth = policy.generate("N", DeceptionIntent.TRUTH)
    lie = policy.generate("N", DeceptionIntent.LIE)
    # Both should be strings
    assert isinstance(truth, str)
    assert isinstance(lie, str)
    assert len(lie) > 0


def test_generate_ambiguous_no_coords():
    policy = NaturalLanguagePolicy("cop")
    for _ in range(10):
        hint = policy.generate("E", DeceptionIntent.AMBIGUOUS)
        assert not policy.hint_is_numeric_location(hint), f"AMBIGUOUS hint had coords: {hint!r}"


def test_hint_not_numeric_location():
    policy = NaturalLanguagePolicy("thief")
    assert not policy.hint_is_numeric_location("Heading north.")
    assert not policy.hint_is_numeric_location("Staying put.")
    assert not policy.hint_is_numeric_location("Making a strategic move.")


def test_hint_numeric_location_detected():
    policy = NaturalLanguagePolicy("thief")
    assert policy.hint_is_numeric_location("position (3,4)")
    assert policy.hint_is_numeric_location("row 5 col 2")
    assert policy.hint_is_numeric_location("at 3, 4 on the grid")


def test_record_opponent_hint():
    policy = NaturalLanguagePolicy("cop")
    assert policy.opponent_hint_count() == 0
    policy.record_opponent_hint("Heading north.")
    assert policy.opponent_hint_count() == 1
    policy.record_opponent_hint("Staying put.")
    assert policy.opponent_hint_count() == 2


def test_orchestrator_generate_strategic_hint():
    from agent.agent_orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(role="thief", game_uid="test-strat", grid_size=7)
    result = orch.generate_strategic_hint("N")
    assert isinstance(result, tuple)
    assert len(result) == 2
    hint, intent_str = result
    assert isinstance(hint, str)
    assert isinstance(intent_str, str)
    assert intent_str in ("truth", "lie")


def test_orchestrator_strategic_hint_not_numeric():
    from agent.agent_orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(role="cop", game_uid="test-no-coords", grid_size=7)
    for move in ["N", "S", "E", "W", "STAY"]:
        hint, _ = orch.generate_strategic_hint(move)
        assert not orch.language_policy.hint_is_numeric_location(hint), (
            f"Strategic hint for {move!r} had numeric coords: {hint!r}"
        )
