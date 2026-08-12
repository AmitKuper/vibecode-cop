"""Competitive-strategy v11 language contracts: intents survive the wire, low budget."""

from __future__ import annotations

from cop_worker.language.deception_policy import DeceptionIntent, NaturalLanguagePolicy
from cop_worker.mcp.messages import ActionMessage, validate_action_message


def test_all_four_language_intents_survive_wire_validation() -> None:
    for intent in DeceptionIntent:
        message = ActionMessage(
            game_id="game_g1",
            step=1,
            role="police",
            config_sha256="0" * 64,
            timestamp="2026-08-06T00:00:00Z",
            phase="reveal",
            move="STAY",
            hint="Making a strategic move.",
            intent=intent.value,
            state_hash="1" * 64,
        )
        assert validate_action_message(message) == (True, None)


def test_language_policy_consumes_context_and_low_token_budget() -> None:
    policy = NaturalLanguagePolicy("police")
    assert (
        policy.choose_intent(
            7,
            belief_entropy=3.0,
            trust_history=[True, False],
            gamelet=4,
            physical_action="E",
            token_budget=4,
        )
        is DeceptionIntent.AMBIGUOUS
    )
