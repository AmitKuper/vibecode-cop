"""Counted-mode recurrent actor-critic policy over local-only observations."""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

import torch
import torch.nn as nn

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape


class RecurrentActorCritic(nn.Module):
    """Compact GRU actor-critic used by the deployed role policies."""

    def __init__(self, input_size: int, n_actions: int, hidden_size: int = 128):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(input_size, hidden_size), nn.Tanh())
        self.memory = nn.GRUCell(hidden_size, hidden_size)
        self.policy_head = nn.Linear(hidden_size, n_actions)
        self.value_head = nn.Linear(hidden_size, 1)

    def forward(
        self, features: torch.Tensor, hidden: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        encoded = self.encoder(features)
        if hidden is None:
            hidden = torch.zeros(encoded.shape[0], self.memory.hidden_size, device=encoded.device)
        next_hidden = self.memory(encoded, hidden)
        return self.policy_head(next_hidden), self.value_head(next_hidden), next_hidden


class RecurrentPolicyLoadError(RuntimeError):
    pass


class RecurrentRolePolicy:
    """Stateful deterministic inference wrapper, one instance per OS process."""

    def __init__(
        self,
        network: RecurrentActorCritic,
        role: str,
        device: torch.device,
        inference_mode: str = "argmax",
        temperature: float | None = None,
    ):
        self.network = network.eval()
        self.role = role
        self.device = device
        self.action_names = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
        self.inference_mode = inference_mode
        self.temperature = temperature
        self._generator = torch.Generator(device="cpu")
        self._generator.manual_seed(secrets.randbits(63))
        self._hidden: torch.Tensor | None = None
        # Inverse of the clamped wire scent law. Stateful (needs the previous frame), so it
        # is reset per episode. Inert unless COPTHIEF_DECODED_SCENT=1.
        self._decoder = None

    def reset(self) -> None:
        self._hidden = None
        if self._decoder is not None:
            self._decoder.reset()

    def _scent_decoder(self, grid_size: int):
        from cop_worker.rl.obs_mode import decoded_scent_enabled
        from cop_worker.scent_decoder import EmitterDecoder

        if not decoded_scent_enabled():
            return None
        if self._decoder is None or self._decoder.n != grid_size:
            self._decoder = EmitterDecoder(grid_size)
        return self._decoder

    def select_action(
        self,
        observation: LocalObservation,
        belief: BeliefState,
        legal_actions: list[str],
    ) -> str:
        if not legal_actions:
            raise RuntimeError("canonical domain returned no legal actions")
        features = torch.tensor(
            local_obs_to_tensor(
                observation, belief, self._scent_decoder(observation.grid_size)
            ),
            dtype=torch.float32,
            device=self.device,
        ).unsqueeze(0)
        with torch.no_grad():
            logits, _value, hidden = self.network(features, self._hidden)
        mask = torch.tensor(
            [action in legal_actions for action in self.action_names],
            dtype=torch.bool,
            device=self.device,
        ).unsqueeze(0)
        if not bool(mask.any()):
            raise RuntimeError("legal-action mask has no deployable action")
        masked = logits.masked_fill(~mask, torch.finfo(logits.dtype).min)
        if self.inference_mode == "low_temp":
            probabilities = torch.softmax(masked.squeeze(0) / self.temperature, dim=-1)
            action_index = int(
                torch.multinomial(probabilities, 1, generator=self._generator).item()
            )
        else:
            action_index = int(masked.argmax(dim=-1).item())
        self._hidden = hidden.detach()
        return self.action_names[action_index]


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
    return RecurrentRolePolicy(
        network,
        role,
        device,
        inference_mode=entry.inference_mode,
        temperature=temperature,
    )


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
