"""Cover result-agreement hashing, signature checks, and bilateral consensus."""

from __future__ import annotations

import pytest

from cop_worker.audit.result_consensus import (
    ResultAgreement,
    ResultConsensusError,
    SignedResultAgreement,
    create_signed_result_agreement,
    verify_bilateral_consensus,
    verify_result_agreement_signature,
)
from cop_worker.step0.signing import generate_key_pair


def _agreement(**overrides) -> ResultAgreement:
    base = {"game_uid": "uid-1", "cop_total_score": 90, "thief_total_score": 30}
    base.update(overrides)
    return ResultAgreement(**base)


def test_agreement_hash_is_stable_hex():
    a = _agreement()
    assert a.agreement_hash() == a.agreement_hash()
    assert len(a.agreement_hash()) == 64


def test_signature_round_trip_and_bad_hex():
    priv, pub = generate_key_pair()
    signed = create_signed_result_agreement(_agreement(), priv)
    assert verify_result_agreement_signature(signed, pub) is True

    corrupt = SignedResultAgreement(agreement=_agreement(), signature_hex="not-hex")
    assert verify_result_agreement_signature(corrupt, pub) is False


def test_bilateral_consensus_agrees_and_detects_byte_mismatch():
    local = SignedResultAgreement(agreement=_agreement(), signature_hex="00")
    same = SignedResultAgreement(agreement=_agreement(), signature_hex="ff")
    # Identical agreements: consensus and canonical bytes both match.
    verify_bilateral_consensus(local, same)

    # timestamp_utc is outside the consensus field set: same consensus hash but
    # different canonical bytes must be rejected as not byte-identical.
    drifted = SignedResultAgreement(
        agreement=_agreement(timestamp_utc="2026-01-01T00:00:00Z"), signature_hex="00"
    )
    with pytest.raises(ResultConsensusError, match="byte-identical"):
        verify_bilateral_consensus(local, drifted)


def test_bilateral_consensus_detects_field_mismatch():
    local = SignedResultAgreement(agreement=_agreement(), signature_hex="00")
    other = SignedResultAgreement(agreement=_agreement(cop_total_score=60), signature_hex="00")
    with pytest.raises(ResultConsensusError, match="consensus mismatch"):
        verify_bilateral_consensus(local, other)
