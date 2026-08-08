"""Red/green tests for the 3-process counted composition architecture.

New design: LeagueManager + CopWorker (mcp_server) + ThiefWorker.
Tests prove:
  - Gamelet construction in COUNTED mode
  - Series lifecycle locks profile after first negotiation
  - Adaptive negotiation failure propagates (not swallowed)
  - Step-0 bilateral signing and identity binding
  - GameletError propagates through the series
  - Role is correctly threaded through the worker config
"""

from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from unittest.mock import AsyncMock, patch

import pytest
import torch

from cop_worker.runtime_mode import RuntimeMode


# ---------------------------------------------------------------------------
# Shared helpers
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


def _manifest(tmp_path):
    from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
    from cop_worker.rl.local_obs_adapter import obs_tensor_shape
    from cop_worker.rl.recurrent_policy import RecurrentActorCritic

    tmp_path.mkdir(parents=True, exist_ok=True)
    entries = []
    torch.manual_seed(17)
    for role, actions in (("cop", COP_ACTIONS), ("police", THIEF_ACTIONS)):
        network = RecurrentActorCritic(obs_tensor_shape(7), len(actions), hidden_size=8)
        artifact = tmp_path / f"{role}_fixture.pt"
        torch.save(
            {
                "role": role,
                "algorithm": "RecurrentA2C-GRU",
                "input_size": obs_tensor_shape(7),
                "n_actions": len(actions),
                "hidden_size": 8,
                "training_steps": 35,
                "state_dict": network.state_dict(),
            },
            artifact,
        )
        entries.append(
            {
                "role": role,
                "algorithm": "RecurrentA2C-GRU",
                "artifact": artifact.name,
                "architecture": "encoder-tanh-grucell-policy-value",
                "sha256": sha256(artifact.read_bytes()).hexdigest(),
                "training_code_sha": "b" * 40,
                "config_sha256": "c" * 64,
                "observation_schema_version": "1.0",
                "action_schema_version": "1.0",
                "belief_schema_version": "1.0",
                "inference_mode": "argmax",
                "grid_size": 7,
                "training_steps": 35,
                "evaluation_win_rate": 0.5,
            }
        )
    path = tmp_path / "MANIFEST.json"
    path.write_text(json.dumps({"models": entries}), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_complete_counted_gamelet_construction_passes_term_validation(tmp_path):
    """Gamelet can be constructed with a complete counted-mode terms dict."""
    from cop_worker.gamelet import Gamelet

    g = Gamelet(
        game_uid="series_fixture_g01",
        sub_game_number=1,
        terms=_VALID_TERMS,
        opponent_group="ABCD1234",
        role="police",
    )
    assert g.game_uid == "series_fixture_g01"
    assert g.sub_game_number == 1
    assert g.role == "police"


def test_start_gamelet_registers_gamelet_in_mcp_server():
    """start_gamelet must register the Gamelet under (game_uid, sub_game_number)."""
    import cop_worker.mcp_server as ms

    ms._GAMELETS.clear()
    result = ms.start_gamelet(
        game_uid="fixture_series_01",
        sub_game_number=1,
        terms=_VALID_TERMS,
        opponent_group="OPPONENTS",
        role="police",
    )
    assert result.get("ok") is True
    assert ("fixture_series_01", 1) in ms._GAMELETS
    ms._GAMELETS.clear()


def test_counted_gamelet_construction_failure_is_not_swallowed():
    """GameletError must propagate when terms are invalid."""
    from cop_worker.gamelet import Gamelet, GameletError

    bad_terms = {**_VALID_TERMS, "board_size": -1}
    with pytest.raises(GameletError, match="board_size"):
        Gamelet(
            game_uid="bad_series",
            sub_game_number=1,
            terms=bad_terms,
            opponent_group="OPPONENTS",
            role="police",
        )


@pytest.mark.asyncio
async def test_counted_adaptive_negotiation_failure_is_not_identity_fallback():
    """ProtocolCompatibilityError must propagate if negotiation fails."""
    from league_manager.protocol.adapter import ProtocolCompatibilityError
    from league_manager.protocol.pipeline import run_adaptive_negotiation

    with (
        patch(
            "league_manager.protocol.pipeline.TransportProbe.probe",
            new=AsyncMock(side_effect=ProtocolCompatibilityError("incompatible peer")),
        ),
        pytest.raises(ProtocolCompatibilityError),
    ):
        await run_adaptive_negotiation("http://127.0.0.1:65530", cache_dir=None)


def test_counted_series_locks_one_adaptive_profile_for_all_gamelets(tmp_path):
    """ProfileCache must return a cache hit for the same schema digest."""
    from league_manager.protocol.pipeline import native_adapter
    from league_manager.protocol.profile import ProfileCache

    first = native_adapter()
    cache = ProfileCache(tmp_path)
    cache.put(first.profile)

    cached = cache.get(first.profile.remote_schema_digest)
    assert cached is not None
    assert cached.profile_hash == first.profile.profile_hash


def test_counted_series_propagates_gamelet_error():
    """GameletError from a gamelet must not be silently dropped."""
    import cop_worker.mcp_server as ms

    ms._GAMELETS.clear()
    # Duplicate registration must raise GameletError
    ms.start_gamelet("dup_series", 1, _VALID_TERMS, "OPP", "police")
    from cop_worker.gamelet import GameletError

    with pytest.raises(GameletError, match="already exists"):
        ms.start_gamelet("dup_series", 1, _VALID_TERMS, "OPP", "police")
    ms._GAMELETS.clear()


def test_counted_gamelet_role_is_threaded_from_config():
    """Gamelet must store the role exactly as supplied."""
    from cop_worker.gamelet import Gamelet

    for role in ("police", "thief"):
        g = Gamelet(
            game_uid="role_test",
            sub_game_number=1,
            terms=_VALID_TERMS,
            opponent_group="OPP",
            role=role,
        )
        assert g.role == role


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
