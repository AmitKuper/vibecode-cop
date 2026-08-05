"""Appendix-E Rule 54 token accounting contracts."""

from __future__ import annotations

import pytest

from agent.audit.result_consensus import (
    GameletOutcome,
    ResultAgreement,
    SignedResultAgreement,
    create_signed_result_agreement,
)
from agent.peer_result import (
    ResultExchangeError,
    _validate_counted_token_accounting,
    _validate_token_totals,
)
from agent.step0.signing import generate_key_pair
from scripts.run_series import _validated_token_totals


def test_token_totals_are_explicit_and_arithmetically_consistent() -> None:
    assert _validated_token_totals() == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    assert (
        _validated_token_totals({"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5})[
            "total_tokens"
        ]
        == 5
    )


@pytest.mark.parametrize(
    "value",
    [
        {"prompt_tokens": True},
        {"prompt_tokens": -1},
        {"prompt_tokens": 1.5},
        {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 3},
    ],
)
def test_invalid_token_accounting_fails_closed(value) -> None:
    with pytest.raises(ValueError, match="token"):
        _validated_token_totals(value)


def test_signed_final_json_roundtrip_keeps_gamelet_and_series_token_totals() -> None:
    private, _public = generate_key_pair()
    gamelet_tokens = {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    series_tokens = {
        "prompt_tokens": 18,
        "completion_tokens": 12,
        "total_tokens": 30,
    }
    agreement = ResultAgreement(
        game_uid="series",
        gamelet_outcomes=[GameletOutcome(1, 20, 5, "cop", 10, token_totals=gamelet_tokens)],
        token_totals=series_tokens,
    )
    signed = create_signed_result_agreement(agreement, private)

    restored = SignedResultAgreement.from_dict(signed.to_dict())

    assert restored.agreement.gamelet_outcomes[0].token_totals == gamelet_tokens
    assert restored.agreement.token_totals == series_tokens
    assert restored.agreement.canonical_bytes() == agreement.canonical_bytes()


@pytest.mark.parametrize(
    "totals",
    [
        {},
        {"prompt_tokens": True, "completion_tokens": 0, "total_tokens": 1},
        {"prompt_tokens": -1, "completion_tokens": 0, "total_tokens": -1},
        {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 3},
    ],
)
def test_peer_rejects_untrusted_token_accounting(totals) -> None:
    with pytest.raises(ResultExchangeError):
        _validate_token_totals(totals, "fixture")


def test_peer_rejects_series_total_that_differs_from_gamelets() -> None:
    outcome = GameletOutcome(1, 20, 5, "cop", 10, token_totals=_validated_token_totals())
    with pytest.raises(ResultExchangeError, match="does not equal gamelet totals"):
        _validate_counted_token_accounting(
            [outcome],
            {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
        )
