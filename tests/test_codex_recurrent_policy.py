"""Deployment-contract tests for the counted recurrent movement policy."""

from __future__ import annotations

import json

import pytest
import torch

from agent.observation import BeliefState, LocalObservation
from agent.rl.action_space import COP_ACTIONS
from agent.rl.local_obs_adapter import obs_tensor_shape
from agent.rl.recurrent_policy import (
    RecurrentActorCritic,
    RecurrentRolePolicy,
    load_recurrent_policy,
)


def _observation() -> LocalObservation:
    return LocalObservation(
        own_position=(3, 3),
        own_barriers_remaining=2,
        known_barriers=[(3, 2)],
        opponent_scent=[[0.0] * 7 for _ in range(7)],
        last_hint="local-only hint",
        step=4,
        gamelet=2,
        grid_size=7,
    )


def test_policy_preserves_recurrent_history_until_explicit_reset():
    torch.manual_seed(11)
    network = RecurrentActorCritic(obs_tensor_shape(7), len(COP_ACTIONS), hidden_size=8)
    policy = RecurrentRolePolicy(network, "cop", torch.device("cpu"))

    policy.select_action(_observation(), BeliefState.uniform(7), ["STAY"])
    first_hidden = policy._hidden.clone()
    policy.select_action(_observation(), BeliefState.uniform(7), ["STAY"])

    assert not torch.equal(first_hidden, policy._hidden)
    policy.reset()
    assert policy._hidden is None


def test_canonical_legal_mask_overrides_illegal_highest_logit():
    network = RecurrentActorCritic(obs_tensor_shape(7), len(COP_ACTIONS), hidden_size=8)
    with torch.no_grad():
        for parameter in network.parameters():
            parameter.zero_()
        network.policy_head.bias[COP_ACTIONS.index("N")] = 100.0
        network.policy_head.bias[COP_ACTIONS.index("STAY")] = 1.0
    policy = RecurrentRolePolicy(network, "cop", torch.device("cpu"))

    selected = policy.select_action(_observation(), BeliefState.uniform(7), ["STAY"])

    assert selected == "STAY"


def test_low_temperature_sampling_never_escapes_canonical_mask():
    network = RecurrentActorCritic(obs_tensor_shape(7), len(COP_ACTIONS), hidden_size=8)
    policy = RecurrentRolePolicy(
        network,
        "cop",
        torch.device("cpu"),
        inference_mode="low_temp",
        temperature=0.5,
    )

    selected = {
        policy.select_action(_observation(), BeliefState.uniform(7), ["STAY"]) for _ in range(20)
    }

    assert selected == {"STAY"}


def test_manifest_checksum_mismatch_fails_closed(tmp_path):
    artifact = tmp_path / "cop.pt"
    artifact.write_bytes(b"tampered checkpoint")
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "role": "cop",
                        "algorithm": "RecurrentA2C-GRU",
                        "artifact": artifact.name,
                        "sha256": "0" * 64,
                        "training_code_sha": "1" * 40,
                        "config_sha256": "2" * 64,
                        "observation_schema_version": "1.0",
                        "action_schema_version": "1.0",
                        "belief_schema_version": "1.0",
                        "inference_mode": "argmax",
                        "grid_size": 7,
                        "training_steps": 35,
                        "evaluation_win_rate": 0.5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        load_recurrent_policy(manifest, "cop")
