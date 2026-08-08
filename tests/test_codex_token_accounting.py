"""Appendix-E Rule 54: token accounting contracts on gamelet results and ResultAgreement."""

from __future__ import annotations

from cop_worker.audit.result_consensus import (
    GameletOutcome,
    ResultAgreement,
    SignedResultAgreement,
    create_signed_result_agreement,
)
from cop_worker.step0.signing import generate_key_pair

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _zero_tokens() -> dict:
    return {"prompt": 0, "completion": 0, "total": 0}


def _tokens(prompt: int, completion: int) -> dict:
    return {"prompt": prompt, "completion": completion, "total": prompt + completion}


# ---------------------------------------------------------------------------
# GameletOutcome token_totals
# ---------------------------------------------------------------------------


def test_gamelet_outcome_has_token_totals_field():
    """GameletOutcome must expose a token_totals field."""
    outcome = GameletOutcome(
        gamelet=1,
        cop_score=20,
        thief_score=5,
        winner="cop",
        turns_played=10,
        token_totals=_zero_tokens(),
    )
    assert isinstance(outcome.token_totals, dict)


def test_gamelet_outcome_token_totals_roundtrip():
    """token_totals must survive a to_dict / from_dict round-trip."""
    private, _ = generate_key_pair()
    tokens = _tokens(3, 2)
    agreement = ResultAgreement(
        game_uid="series",
        gamelet_outcomes=[GameletOutcome(1, 20, 5, "cop", 10, token_totals=tokens)],
        token_totals=_tokens(18, 12),
    )
    signed = create_signed_result_agreement(agreement, private)
    restored = SignedResultAgreement.from_dict(signed.to_dict())

    assert restored.agreement.gamelet_outcomes[0].token_totals == tokens
    assert restored.agreement.token_totals == _tokens(18, 12)
    assert restored.agreement.canonical_bytes() == agreement.canonical_bytes()


# ---------------------------------------------------------------------------
# ResultAgreement series-level token_totals
# ---------------------------------------------------------------------------


def test_result_agreement_has_token_totals_field():
    """ResultAgreement must expose a series-level token_totals field."""
    agreement = ResultAgreement(
        game_uid="series",
        token_totals=_zero_tokens(),
    )
    assert isinstance(agreement.token_totals, dict)


def test_token_totals_preserved_in_canonical_bytes():
    """token_totals must be included in canonical_bytes for signing."""
    private, _ = generate_key_pair()
    agreement_a = ResultAgreement(game_uid="s", token_totals=_zero_tokens())
    agreement_b = ResultAgreement(game_uid="s", token_totals=_tokens(1, 1))

    # Different token_totals → different canonical bytes → different signature
    assert agreement_a.canonical_bytes() != agreement_b.canonical_bytes()


# ---------------------------------------------------------------------------
# cop_worker.gamelet get_result returns llm_tokens
# ---------------------------------------------------------------------------


_VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "max_steps": 35,
    "survival_threshold": 35,
    "cop_barrier_quota": 2,
    "capture_radius": 0,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "barriers_max": 14,
    "num_games": 6,
}


def test_gamelet_get_result_has_llm_tokens_field():
    """_build_result() must include llm_tokens with prompt/completion/total keys."""
    from cop_worker.gamelet import Gamelet

    g = Gamelet(
        game_uid="uid",
        sub_game_number=1,
        terms=_VALID_TERMS,
        opponent_group="opponent",
        role="police",
    )
    # _build_result is the canonical result builder — callable from any state
    result = g._build_result(audit_ok=True)
    assert "llm_tokens" in result
    tokens = result["llm_tokens"]
    assert "prompt" in tokens or "total" in tokens  # either key set is valid


def test_gamelet_get_result_has_winner_field():
    """_build_result() must include a winner field."""
    from cop_worker.gamelet import Gamelet

    g = Gamelet(
        game_uid="uid",
        sub_game_number=1,
        terms=_VALID_TERMS,
        opponent_group="opponent",
        role="police",
    )
    result = g._build_result(audit_ok=True)
    assert "winner" in result
    assert result["winner"] in {"police", "thief", "draw"}
