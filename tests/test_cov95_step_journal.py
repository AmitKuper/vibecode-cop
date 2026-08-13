"""Cover StepJournal validation, chain-failure, and seal_nonces branches."""

from __future__ import annotations

import pytest

from cop_worker.audit.step_journal import StepEvidence, StepJournal


def _ev(step: int, role: str = "cop", gamelet: int = 1, game_uid: str = "g-001") -> StepEvidence:
    return StepEvidence(
        game_uid=game_uid,
        gamelet=gamelet,
        step=step,
        role=role,
        local_nonce=f"n{step}",
    )


def test_append_rejects_non_contiguous_step(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    with pytest.raises(ValueError, match="contiguous"):
        j.append(_ev(2))  # first entry must be step 1


def test_append_rejects_negative_gamelet(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    with pytest.raises(ValueError, match="one-based"):
        j.append(_ev(1, gamelet=-1))


def test_append_rejects_invalid_role(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    with pytest.raises(ValueError, match="invalid journal role"):
        j.append(_ev(1, role="robber"))


def test_append_rejects_identity_change(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    j.append(_ev(1))
    with pytest.raises(ValueError, match="identity changed"):
        j.append(_ev(2, game_uid="different"))


def test_verify_chain_detects_step_mismatch(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    j.append(_ev(1))
    j.append(_ev(2))
    j._entries[1].step = 9  # corrupt the recorded step
    ok, msg = j.verify_chain()
    assert not ok and "step mismatch" in msg


def test_verify_chain_detects_identity_mismatch(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    j.append(_ev(1))
    j.append(_ev(2))
    j._entries[1].game_uid = "tampered"  # identity check precedes hash check
    ok, msg = j.verify_chain()
    assert not ok and "identity mismatch" in msg


def test_verify_chain_detects_transcript_hash_mismatch(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    j.append(_ev(1))
    # canonical_bytes ignores transcript_hash, so the chain hash still recomputes,
    # but the stored per-entry transcript_hash now disagrees.
    j._entries[0].transcript_hash = "0" * 64
    ok, msg = j.verify_chain()
    assert not ok and "transcript hash mismatch" in msg


def test_verify_chain_detects_wrong_expected_steps(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    j.append(_ev(1))
    ok, msg = j.verify_chain(expected_steps=5)
    assert not ok and "expected 5" in msg


def test_seal_nonces_rebuilds_chain(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    j.append(_ev(1))
    j.append(_ev(2))
    root = j.seal_nonces({1: "ln1", 2: "ln2"}, {1: "rn1", 2: "rn2"}, expected_steps=2)
    assert root == j.transcript_root()
    assert j.entries[0].received_nonce == "rn1"
    ok, _msg = j.verify_chain(expected_steps=2)
    assert ok


def test_seal_nonces_rejects_mismatched_nonce_sets(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    j.append(_ev(1))
    j.append(_ev(2))
    with pytest.raises(ValueError, match="nonce sets must exactly match"):
        j.seal_nonces({1: "a"}, {1: "b", 2: "c"}, expected_steps=2)


def test_seal_nonces_rejects_wrong_extent(tmp_path):
    j = StepJournal(str(tmp_path / "j.json"))
    j.append(_ev(1))
    with pytest.raises(ValueError, match="journal extent"):
        j.seal_nonces({1: "a", 2: "b"}, {1: "c", 2: "d"}, expected_steps=2)
