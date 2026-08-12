"""Targeted tests for modules the 2026-08-10 additions left under the CI coverage gate.

This part pins the Dueling counted-policy loader's happy path and refusal branches.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
import torch

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.counted_policy import (
    CountedPolicyLoadError,
    DuelingDoubleQNetwork,
    DuelingDoubleQRolePolicy,
    _load_dueling_policy,
)
from cop_worker.rl.local_obs_adapter import obs_tensor_shape


def _dueling_checkpoint(tmp_path, **overrides):
    payload = {
        "role": "thief",
        "algorithm": "DuelingDoubleDQN",
        "input_size": obs_tensor_shape(7),
        "n_actions": 5,
        "hidden_size": 32,
    }
    payload.update(overrides)
    net = DuelingDoubleQNetwork(payload["input_size"], payload["n_actions"], payload["hidden_size"])
    payload["state_dict"] = net.state_dict()
    artifact = tmp_path / "thief_test.pt"
    torch.save(payload, artifact)
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    entry = SimpleNamespace(
        inference_mode="argmax",
        artifact=artifact.name,
        sha256=sha,
        algorithm="DuelingDoubleDQN",
    )
    return tmp_path / "MANIFEST.json", entry


class TestDuelingLoader:
    def test_happy_path_loads_and_selects_a_legal_action(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path)
        policy = _load_dueling_policy(manifest, entry, "thief")
        assert isinstance(policy, DuelingDoubleQRolePolicy)
        obs = LocalObservation(
            own_position=(3, 3),
            own_barriers_remaining=0,
            known_barriers=[],
            opponent_scent=[[0.0] * 7 for _ in range(7)],
            last_hint="",
            step=1,
            gamelet=1,
            grid_size=7,
        )
        action = policy.select_action(obs, BeliefState.uniform(7, step=1), ["N", "S"])
        assert action in {"N", "S"}
        policy.reset()  # no decoder configured: must be a no-op, never raise

    def test_no_legal_actions_is_a_hard_error(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path)
        policy = _load_dueling_policy(manifest, entry, "thief")
        obs = LocalObservation(
            own_position=(3, 3),
            own_barriers_remaining=0,
            known_barriers=[],
            opponent_scent=[[0.0] * 7 for _ in range(7)],
            last_hint="",
            step=1,
            gamelet=1,
            grid_size=7,
        )
        with pytest.raises(RuntimeError, match="no legal actions"):
            policy.select_action(obs, BeliefState.uniform(7, step=1), [])

    def test_role_mismatch_refuses(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path)
        with pytest.raises(CountedPolicyLoadError, match="role"):
            _load_dueling_policy(manifest, entry, "cop")

    def test_wrong_input_size_refuses(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path, input_size=17)
        with pytest.raises(CountedPolicyLoadError, match="observation tensor"):
            _load_dueling_policy(manifest, entry, "thief")

    def test_wrong_action_count_refuses(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path, n_actions=9)
        with pytest.raises(CountedPolicyLoadError, match="action schema"):
            _load_dueling_policy(manifest, entry, "thief")

    def test_non_argmax_inference_refuses(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path)
        entry.inference_mode = "sample"
        with pytest.raises(CountedPolicyLoadError, match="argmax"):
            _load_dueling_policy(manifest, entry, "thief")

    def test_missing_artifact_refuses(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path)
        entry.artifact = "no_such_file.pt"
        with pytest.raises(CountedPolicyLoadError, match="not found"):
            _load_dueling_policy(manifest, entry, "thief")
