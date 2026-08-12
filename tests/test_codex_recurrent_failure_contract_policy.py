"""Failure-closed branch contracts for the counted recurrent policy runtime."""

from __future__ import annotations

import pytest
import torch

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import obs_tensor_shape
from cop_worker.rl.recurrent_policy import (
    RecurrentActorCritic,
    RecurrentRolePolicy,
    file_sha256,
)


def _observation() -> LocalObservation:
    return LocalObservation(
        own_position=(3, 3),
        own_barriers_remaining=2,
        known_barriers=[],
        opponent_scent=[[0.0] * 7 for _ in range(7)],
        last_hint="safe",
        step=1,
        gamelet=1,
        grid_size=7,
    )


def test_policy_rejects_empty_and_undeployable_legal_masks() -> None:
    policy = RecurrentRolePolicy(
        RecurrentActorCritic(obs_tensor_shape(7), len(COP_ACTIONS), hidden_size=8),
        "cop",
        torch.device("cpu"),
    )
    with pytest.raises(RuntimeError, match="no legal actions"):
        policy.select_action(_observation(), BeliefState.uniform(7), [])
    with pytest.raises(RuntimeError, match="no deployable action"):
        policy.select_action(_observation(), BeliefState.uniform(7), ["ALIEN"])

    thief = RecurrentRolePolicy(
        RecurrentActorCritic(obs_tensor_shape(7), len(THIEF_ACTIONS), hidden_size=8),
        "police",
        torch.device("cpu"),
    )
    assert thief.action_names == THIEF_ACTIONS


def test_file_sha256_reads_artifact_chunks(tmp_path) -> None:
    artifact = tmp_path / "large.bin"
    artifact.write_bytes(b"a" * (1024 * 1024 + 3))
    assert len(file_sha256(artifact)) == 64
