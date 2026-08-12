"""Checked loading of the manifest-selected recurrent counted artifact.

Split out of ``cop_worker.rl.recurrent_policy`` (which remains the public facade
and re-exports these names). Imported at the bottom of that module, after the
network/policy/error classes exist, so the top-level imports here are safe.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import torch

from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import obs_tensor_shape
from cop_worker.rl.recurrent_policy import (
    RecurrentActorCritic,
    RecurrentPolicyLoadError,
    RecurrentRolePolicy,
)


def load_recurrent_policy(manifest_path: str | Path, role: str) -> RecurrentRolePolicy:
    """Load the exact manifest-selected artifact and verify its checksum/schema."""
    from cop_worker.rl.model_schema import load_manifest, validate_model_file

    manifest_path = Path(manifest_path)
    entries = load_manifest(str(manifest_path))
    if role not in entries:
        raise RecurrentPolicyLoadError(f"manifest has no {role!r} policy")
    entry = entries[role]
    if entry.algorithm != "RecurrentA2C-GRU":
        raise RecurrentPolicyLoadError(
            f"counted policy must be RecurrentA2C-GRU, got {entry.algorithm!r}"
        )
    if not entry.artifact:
        raise RecurrentPolicyLoadError("manifest entry omits model artifact")
    artifact = manifest_path.parent / entry.artifact
    if not artifact.is_file():
        raise RecurrentPolicyLoadError(f"model artifact not found: {artifact}")
    validate_model_file(str(artifact), entry.sha256)
    device = torch.device("cpu")
    checkpoint = torch.load(artifact, map_location=device, weights_only=True)
    expected_role = checkpoint.get("role")
    if expected_role != role:
        raise RecurrentPolicyLoadError(f"checkpoint role {expected_role!r} does not match {role!r}")
    if checkpoint.get("algorithm") != entry.algorithm:
        raise RecurrentPolicyLoadError("checkpoint algorithm does not match manifest")
    input_size = int(checkpoint["input_size"])
    if input_size != obs_tensor_shape(entry.grid_size):
        raise RecurrentPolicyLoadError("checkpoint observation tensor schema is incompatible")
    hidden_size = int(checkpoint["hidden_size"])
    if hidden_size <= 0 or hidden_size > 2048:
        raise RecurrentPolicyLoadError("checkpoint recurrent hidden size is invalid")
    network = RecurrentActorCritic(
        input_size=input_size,
        n_actions=int(checkpoint["n_actions"]),
        hidden_size=hidden_size,
    ).to(device)
    network.load_state_dict(checkpoint["state_dict"])
    expected_actions = len(COP_ACTIONS if role == "cop" else THIEF_ACTIONS)
    if int(checkpoint["n_actions"]) != expected_actions:
        raise RecurrentPolicyLoadError("checkpoint action schema is incompatible")
    if entry.inference_mode not in {"argmax", "low_temp"}:
        raise RecurrentPolicyLoadError("manifest inference mode is unsupported")
    temperature = None
    if entry.inference_mode == "low_temp":
        temperature = float(entry.hyperparams.get("inference_temperature", 0.0))
        if not 0 < temperature <= 1:
            raise RecurrentPolicyLoadError("low_temp inference temperature must be in (0, 1]")
    network.eval()
    policy = RecurrentRolePolicy(
        network,
        role,
        device,
        inference_mode=entry.inference_mode,
        temperature=temperature,
    )
    recorded = dict(getattr(entry, "obs_mode", None) or {})
    policy.use_decoded_scent = bool(recorded.get("decoded_scent"))
    return policy


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
