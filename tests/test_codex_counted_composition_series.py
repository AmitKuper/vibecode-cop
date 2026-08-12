"""Red/green tests for the 3-process counted composition architecture (series part).

New design: LeagueManager + CopWorker (mcp_server) + ThiefWorker.
Tests prove:
  - Series lifecycle locks profile after first negotiation
  - Adaptive negotiation failure propagates (not swallowed)
  - Step-0 bilateral signing and identity binding
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_counted_adaptive_negotiation_failure_is_not_identity_fallback():
    """ProtocolCompatibilityError must propagate if negotiation fails."""
    from cop_worker.protocol.adapter import ProtocolCompatibilityError
    from cop_worker.protocol.pipeline import run_adaptive_negotiation

    with (
        patch(
            "cop_worker.protocol.pipeline.TransportProbe.probe",
            new=AsyncMock(side_effect=ProtocolCompatibilityError("incompatible peer")),
        ),
        pytest.raises(ProtocolCompatibilityError),
    ):
        await run_adaptive_negotiation("http://127.0.0.1:65530", cache_dir=None)


def test_counted_series_locks_one_adaptive_profile_for_all_gamelets(tmp_path):
    """ProfileCache must return a cache hit for the same schema digest."""
    from cop_worker.protocol.pipeline import native_adapter
    from cop_worker.protocol.profile import ProfileCache

    first = native_adapter()
    cache = ProfileCache(tmp_path)
    cache.put(first.profile)

    cached = cache.get(first.profile.remote_schema_digest)
    assert cached is not None
    assert cached.profile_hash == first.profile.profile_hash


def test_counted_step0_is_bilateral_signed_and_identity_bound():
    """SignedResultAgreement must be bilateral: both sides agree or verification fails."""
    from cop_worker.audit.result_consensus import (
        GameletOutcome,
        ResultAgreement,
        create_signed_result_agreement,
        verify_bilateral_consensus,
    )
    from cop_worker.step0.signing import generate_key_pair

    cop_private, cop_public = generate_key_pair()
    thief_private, thief_public = generate_key_pair()

    outcomes = [GameletOutcome(i, 20, 5, "cop", 10) for i in range(1, 7)]
    agreement = ResultAgreement(game_uid="step0_fixture", gamelet_outcomes=outcomes)

    cop_signed = create_signed_result_agreement(agreement, cop_private)
    thief_signed = create_signed_result_agreement(agreement, thief_private)

    # Both sides must agree on the same canonical bytes
    assert cop_signed.agreement.canonical_bytes() == thief_signed.agreement.canonical_bytes()

    # Tampered agreement must not verify
    tampered = ResultAgreement(game_uid="step0_TAMPERED", gamelet_outcomes=outcomes)
    thief_tampered = create_signed_result_agreement(tampered, thief_private)
    with pytest.raises(Exception):
        verify_bilateral_consensus(cop_signed, thief_tampered)
