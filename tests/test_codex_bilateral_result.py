"""Bilateral result agreement must be signed, byte-identical, and nonce-free."""

from __future__ import annotations

from dataclasses import asdict

from cop_worker.audit.result_consensus import (
    GameletOutcome,
    ResultAgreement,
    ResultConsensusError,
    SignedResultAgreement,
    create_signed_result_agreement,
    verify_bilateral_consensus,
)
from cop_worker.step0.signing import generate_key_pair

import pytest


def _make_agreement(game_uid: str = "series_fixture") -> ResultAgreement:
    """Build a minimal 6-gamelet ResultAgreement."""
    outcomes = [
        GameletOutcome(
            gamelet=i,
            cop_score=20,
            thief_score=5,
            winner="cop",
            turns_played=10,
        )
        for i in range(1, 7)
    ]
    return ResultAgreement(
        game_uid=game_uid,
        gamelet_outcomes=outcomes,
        cop_total_score=120,
        thief_total_score=30,
        series_winner="cop",
    )


def test_bilateral_signing_and_verification():
    """Both peers sign identical agreement; verify_bilateral_consensus must pass."""
    private_a, _ = generate_key_pair()
    private_b, _ = generate_key_pair()
    agreement = _make_agreement()

    signed_a = create_signed_result_agreement(agreement, private_a)
    signed_b = create_signed_result_agreement(agreement, private_b)

    # Should not raise — same canonical bytes
    verify_bilateral_consensus(signed_a, signed_b)


def test_bilateral_consensus_detects_mismatch():
    """verify_bilateral_consensus raises on disagreeing winner fields."""
    private_a, _ = generate_key_pair()
    private_b, _ = generate_key_pair()

    agreement_a = _make_agreement()
    agreement_b = ResultAgreement(
        game_uid="series_fixture",
        gamelet_outcomes=[GameletOutcome(1, 20, 5, "cop", 10)],
        series_winner="thief",  # disagrees
    )
    signed_a = create_signed_result_agreement(agreement_a, private_a)
    signed_b = create_signed_result_agreement(agreement_b, private_b)

    with pytest.raises(ResultConsensusError):
        verify_bilateral_consensus(signed_a, signed_b)


def test_gamelet_outcome_has_winner_field():
    """GameletOutcome must expose a winner field (cop | thief | draw)."""
    outcome = GameletOutcome(gamelet=1, cop_score=20, thief_score=5, winner="cop", turns_played=10)
    assert outcome.winner in {"cop", "thief", "draw"}


def test_signed_result_agreement_roundtrip():
    """to_dict / from_dict round-trip must preserve all gamelet outcomes."""
    private, _ = generate_key_pair()
    agreement = _make_agreement()
    signed = create_signed_result_agreement(agreement, private)

    restored = SignedResultAgreement.from_dict(signed.to_dict())

    assert restored.agreement.canonical_bytes() == agreement.canonical_bytes()
    assert len(restored.agreement.gamelet_outcomes) == 6


def test_get_result_does_not_expose_nonces():
    """The serialised result agreement must not contain raw nonce material."""
    private, _ = generate_key_pair()
    agreement = _make_agreement()
    signed = create_signed_result_agreement(agreement, private)
    serialised = signed.to_dict()

    assert "nonce" not in str(serialised)
    assert "nonces" not in str(serialised)
    assert "nonce_log" not in str(serialised)


def test_gamelet_outcomes_serialise_as_list_of_dicts():
    """Nested outcomes must serialise to list[dict] with a gamelet key."""
    private, _ = generate_key_pair()
    agreement = _make_agreement()
    signed = create_signed_result_agreement(agreement, private)
    restored = SignedResultAgreement.from_dict(signed.to_dict())

    encoded = str(signed.to_dict())
    assert "gamelet" in encoded
    assert len(restored.agreement.gamelet_outcomes) == 6
