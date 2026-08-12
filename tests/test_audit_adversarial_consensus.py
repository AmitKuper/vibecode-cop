"""Adversarial tests for Phase 6 audit primitives.

Tests cover:
- AuditSummary signing and verification
- ResultAgreement bilateral consensus
"""

from __future__ import annotations

import pytest

from cop_worker.audit.audit_summary import (
    AuditSummary,
    create_signed_audit_summary,
    verify_audit_summary,
)
from cop_worker.audit.result_consensus import (
    GameletOutcome,
    ResultAgreement,
    ResultConsensusError,
    SignedResultAgreement,
    verify_bilateral_consensus,
)
from cop_worker.step0.signing import generate_key_pair

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agreement(
    game_uid: str = "game-001",
    winner: str = "cop",
    cop_score: int = 3,
    thief_score: int = 1,
) -> ResultAgreement:
    return ResultAgreement(
        game_uid=game_uid,
        gamelet_outcomes=[
            GameletOutcome(
                gamelet=1,
                cop_score=cop_score,
                thief_score=thief_score,
                winner=winner,
                turns_played=10,
            )
        ],
        cop_total_score=cop_score,
        thief_total_score=thief_score,
        series_winner=winner,
        counted_status=True,
    )


def _signed_agreement(agreement: ResultAgreement) -> SignedResultAgreement:
    return SignedResultAgreement(agreement, "fakesig")


# ---------------------------------------------------------------------------
# 6B: AuditSummary signing
# ---------------------------------------------------------------------------


def test_audit_summary_sign_verify():
    """Signing then verifying an audit summary should return True."""
    priv, pub = generate_key_pair()
    summary = AuditSummary(
        game_uid="game-001",
        gamelet=1,
        audit_status="PASSED",
        verified_steps=5,
        expected_steps=5,
        public_key_hex=pub.hex(),
    )
    signed = create_signed_audit_summary(summary, priv)
    assert verify_audit_summary(signed)


def test_audit_summary_tampered():
    """Changing a field after signing should fail verification."""
    priv, pub = generate_key_pair()
    summary = AuditSummary(
        game_uid="game-001",
        gamelet=1,
        audit_status="PASSED",
        verified_steps=5,
        expected_steps=5,
        public_key_hex=pub.hex(),
    )
    signed = create_signed_audit_summary(summary, priv)
    # Tamper after signing
    signed.summary.verified_steps = 0
    assert not verify_audit_summary(signed)


# ---------------------------------------------------------------------------
# 6C: ResultAgreement bilateral consensus
# ---------------------------------------------------------------------------


def test_bilateral_consensus_match():
    """Identical agreements from both peers should not raise."""
    a = _signed_agreement(_make_agreement())
    b = _signed_agreement(_make_agreement())
    # Should not raise
    verify_bilateral_consensus(a, b)


def test_bilateral_consensus_mismatch():
    """Different series winners should raise ResultConsensusError."""
    a = _signed_agreement(_make_agreement(winner="cop"))
    b = _signed_agreement(_make_agreement(winner="police"))
    with pytest.raises(ResultConsensusError, match="consensus mismatch"):
        verify_bilateral_consensus(a, b)


def test_result_consensus_tampered_score():
    """A tampered total score should cause a consensus mismatch."""
    base = _make_agreement(cop_score=3, thief_score=1)
    tampered = _make_agreement(cop_score=0, thief_score=1)  # cop score changed
    a = _signed_agreement(base)
    b = _signed_agreement(tampered)
    with pytest.raises(ResultConsensusError):
        verify_bilateral_consensus(a, b)


def test_result_consensus_gamelet_reorder():
    """Reordered gamelet outcomes produce a different consensus hash."""
    outcome1 = GameletOutcome(gamelet=1, cop_score=2, thief_score=0, winner="cop", turns_played=5)
    outcome2 = GameletOutcome(
        gamelet=2, cop_score=0, thief_score=2, winner="police", turns_played=5
    )

    agreement_a = ResultAgreement(
        game_uid="game-001",
        gamelet_outcomes=[outcome1, outcome2],
        cop_total_score=2,
        thief_total_score=2,
        series_winner="draw",
    )
    agreement_b = ResultAgreement(
        game_uid="game-001",
        gamelet_outcomes=[outcome2, outcome1],  # reversed order
        cop_total_score=2,
        thief_total_score=2,
        series_winner="draw",
    )
    # Reordered gamelets should produce different hashes
    assert agreement_a.consensus_fields_hash() != agreement_b.consensus_fields_hash()
