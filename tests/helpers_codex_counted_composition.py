"""Shared fixtures for the counted-composition test modules (base and _lm variants)."""

from __future__ import annotations

import json
from hashlib import sha256

import torch

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
