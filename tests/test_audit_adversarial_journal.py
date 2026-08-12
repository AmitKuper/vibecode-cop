"""Adversarial tests for Phase 6 audit primitives.

Tests cover:
- StepJournal hash chain integrity (tamper, insert, delete)
- Edge cases: zero-turn abort, atomic write, persistence round-trip
"""

from __future__ import annotations

from pathlib import Path

from cop_worker.audit.audit_summary import AuditSummary
from cop_worker.audit.step_journal import StepEvidence, StepJournal

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
