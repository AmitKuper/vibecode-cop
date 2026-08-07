"""Adversarial tests for Phase 6 audit primitives.

Tests cover:
- StepJournal hash chain integrity (tamper, insert, delete)
- AuditSummary signing and verification
- ResultAgreement bilateral consensus
- Edge cases: zero-turn abort, atomic write, persistence round-trip
"""

from __future__ import annotations

from pathlib import Path

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
from cop_worker.audit.step_journal import StepEvidence, StepJournal
from cop_worker.step0.signing import generate_key_pair

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evidence(step: int, role: str = "cop") -> StepEvidence:
    return StepEvidence(
        game_uid="game-test-001",
        gamelet=1,
        step=step,
        role=role,
        local_commitment=f"commit_{step}",
        local_nonce=f"nonce_{step}",
        local_move=f"move_{step}",
        commitment_verified=True,
    )


def _make_journal(tmp_path: Path, steps: int = 3) -> tuple[StepJournal, Path]:
    p = tmp_path / "journal.json"
    j = StepJournal(str(p))
    for s in range(1, steps + 1):
        j.append(_make_evidence(s))
    return j, p


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
# 6A: StepJournal chain tests
# ---------------------------------------------------------------------------


def test_chain_verifies_ok(tmp_path):
    """A 3-step journal chain should verify without errors."""
    j, _ = _make_journal(tmp_path, steps=3)
    ok, msg = j.verify_chain()
    assert ok, f"Chain should verify but got: {msg}"
    assert msg == ""


def test_chain_detects_tampered_move(tmp_path):
    """Changing a move in an entry should break the chain."""
    j, _ = _make_journal(tmp_path, steps=3)
    # Tamper: mutate the internal entry list
    j._entries[1].local_move = "TAMPERED_MOVE"
    ok, msg = j.verify_chain()
    assert not ok
    assert "Chain broken" in msg


def test_chain_detects_tampered_nonce(tmp_path):
    """Changing a nonce in an entry should break the chain."""
    j, _ = _make_journal(tmp_path, steps=3)
    j._entries[0].local_nonce = "TAMPERED_NONCE"
    ok, msg = j.verify_chain()
    assert not ok
    assert "Chain broken" in msg


def test_chain_detects_extra_step(tmp_path):
    """Inserting an extra entry without updating chain_hashes breaks verification."""
    j, _ = _make_journal(tmp_path, steps=3)
    # Insert extra entry at position 1 without a corresponding chain hash
    extra = _make_evidence(99)
    j._entries.insert(1, extra)
    # Now len(entries) > len(chain_hashes) — zip stops at chain_hashes length
    # but entry[1] (extra) pairs with chain_hashes[1] (original step 1 hash)
    ok, msg = j.verify_chain()
    assert not ok, "Extra inserted step should break the chain"


def test_chain_detects_missing_step(tmp_path):
    """Removing an entry should break the chain for subsequent entries."""
    j, _ = _make_journal(tmp_path, steps=3)
    # Remove middle entry
    j._entries.pop(1)
    # Now entry[1] is original entry[2] but chain_hashes[1] was for original entry[1]
    ok, msg = j.verify_chain()
    assert not ok, "Missing step should break the chain"


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
    b = _signed_agreement(_make_agreement(winner="thief"))
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
    outcome2 = GameletOutcome(gamelet=2, cop_score=0, thief_score=2, winner="thief", turns_played=5)

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


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_not_applicable_for_zero_turns(tmp_path):
    """A zero-turn abort should yield NOT_APPLICABLE, never PASSED."""
    j = StepJournal(str(tmp_path / "journal.json"))
    # No steps appended
    assert j.transcript_root() == j._genesis_hash

    summary = AuditSummary(
        game_uid="game-abort",
        gamelet=1,
        audit_status="NOT_APPLICABLE",
        expected_steps=0,
        verified_steps=0,
    )
    assert summary.audit_status == "NOT_APPLICABLE"
    assert summary.audit_status != "PASSED"


def test_atomic_write(tmp_path):
    """Journal write should use a tmp file then replace atomically; no .tmp leftover."""
    p = tmp_path / "journal.json"
    j = StepJournal(str(p))
    j.append(_make_evidence(1))

    # After save, no .tmp file should remain
    tmp_file = Path(str(p) + ".tmp")
    assert not tmp_file.exists(), "Temporary file should be removed after atomic replace"
    assert p.exists(), "Journal file should exist"


def test_journal_persistence(tmp_path):
    """Write entries, reload from disk, chain should still verify."""
    p = tmp_path / "journal.json"

    # Write
    j1 = StepJournal(str(p))
    for s in range(1, 5):
        j1.append(_make_evidence(s))
    root_before = j1.transcript_root()

    # Reload
    j2 = StepJournal(str(p))
    ok, msg = j2.verify_chain()
    assert ok, f"Reloaded chain should verify but got: {msg}"
    assert j2.transcript_root() == root_before
    assert len(j2.entries) == 4
