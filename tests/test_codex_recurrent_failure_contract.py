"""Failure-closed branch contracts for counted recurrent model loading."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import obs_tensor_shape
from cop_worker.rl.recurrent_policy import (
    RecurrentActorCritic,
    RecurrentPolicyLoadError,
    RecurrentRolePolicy,
    file_sha256,
    load_recurrent_policy,
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


def _entry(**overrides):
    values = {
        "algorithm": "RecurrentA2C-GRU",
        "artifact": "model.pt",
        "sha256": "0" * 64,
        "grid_size": 7,
        "inference_mode": "argmax",
        "hyperparams": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _checkpoint(**overrides):
    network = RecurrentActorCritic(obs_tensor_shape(7), len(COP_ACTIONS), hidden_size=8)
    values = {
        "role": "cop",
        "algorithm": "RecurrentA2C-GRU",
        "input_size": obs_tensor_shape(7),
        "hidden_size": 8,
        "n_actions": len(COP_ACTIONS),
        "state_dict": network.state_dict(),
    }
    values.update(overrides)
    return values


def _checkpoint_with_actions(n_actions: int):
    network = RecurrentActorCritic(obs_tensor_shape(7), n_actions, hidden_size=8)
    return _checkpoint(n_actions=n_actions, state_dict=network.state_dict())


def _patch_loader(monkeypatch, tmp_path, *, entry=None, checkpoint=None):
    artifact = tmp_path / "model.pt"
    artifact.write_bytes(b"checkpoint")
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text("{}", encoding="utf-8")
    chosen_entry = entry or _entry()
    monkeypatch.setattr(
        "cop_worker.rl.model_schema.load_manifest", lambda _path: {"cop": chosen_entry}
    )
    monkeypatch.setattr("cop_worker.rl.model_schema.validate_model_file", lambda *_args: None)
    monkeypatch.setattr(torch, "load", lambda *_args, **_kwargs: checkpoint or _checkpoint())
    return manifest


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


def test_loader_rejects_missing_role(monkeypatch, tmp_path) -> None:
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("cop_worker.rl.model_schema.load_manifest", lambda _path: {})
    with pytest.raises(RecurrentPolicyLoadError, match="manifest has no"):
        load_recurrent_policy(manifest, "cop")


@pytest.mark.parametrize(
    ("entry", "match"),
    [
        (_entry(algorithm="DQN"), "must be RecurrentA2C"),
        (_entry(artifact=""), "omits model artifact"),
        (_entry(artifact="missing.pt"), "artifact not found"),
    ],
)
def test_loader_rejects_bad_manifest_entry(monkeypatch, tmp_path, entry, match) -> None:
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("cop_worker.rl.model_schema.load_manifest", lambda _path: {"cop": entry})
    with pytest.raises(RecurrentPolicyLoadError, match=match):
        load_recurrent_policy(manifest, "cop")


@pytest.mark.parametrize(
    ("checkpoint", "entry", "match"),
    [
        (_checkpoint(role="police"), _entry(), "does not match"),
        (_checkpoint(algorithm="DQN"), _entry(), "algorithm does not match"),
        (_checkpoint(input_size=1), _entry(), "observation tensor schema"),
        (_checkpoint(hidden_size=0), _entry(), "hidden size is invalid"),
        (_checkpoint(hidden_size=2049), _entry(), "hidden size is invalid"),
        (_checkpoint_with_actions(1), _entry(), "action schema"),
        (_checkpoint(), _entry(inference_mode="random"), "inference mode is unsupported"),
        (
            _checkpoint(),
            _entry(inference_mode="low_temp", hyperparams={"inference_temperature": 0}),
            "temperature must be",
        ),
        (
            _checkpoint(),
            _entry(inference_mode="low_temp", hyperparams={"inference_temperature": 1.1}),
            "temperature must be",
        ),
    ],
)
def test_loader_rejects_incompatible_checkpoint(
    monkeypatch, tmp_path, checkpoint, entry, match
) -> None:
    manifest = _patch_loader(
        monkeypatch,
        tmp_path,
        entry=entry,
        checkpoint=checkpoint,
    )
    with pytest.raises(RecurrentPolicyLoadError, match=match):
        load_recurrent_policy(manifest, "cop")


def test_loader_accepts_valid_low_temperature_checkpoint(monkeypatch, tmp_path) -> None:
    manifest = _patch_loader(
        monkeypatch,
        tmp_path,
        entry=_entry(inference_mode="low_temp", hyperparams={"inference_temperature": 0.2}),
    )
    policy = load_recurrent_policy(manifest, "cop")
    assert policy.temperature == 0.2
    assert policy.inference_mode == "low_temp"


def test_file_sha256_reads_artifact_chunks(tmp_path) -> None:
    artifact = tmp_path / "large.bin"
    artifact.write_bytes(b"a" * (1024 * 1024 + 3))
    assert len(file_sha256(artifact)) == 64
