"""Dueling-DDQN counted inference: network, masked-argmax adapter, checked loader.

Split out of ``cop_worker.rl.counted_policy`` (which remains the public facade and
re-exports every name here); the loader raises the facade's
``CountedPolicyLoadError`` so exception identity is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import torch
import torch.nn as nn

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape


class DuelingDoubleQNetwork(nn.Module):
    """Feed-forward dueling Q network used by the selected thief policy."""

    def __init__(self, input_size: int, n_actions: int, hidden_size: int = 256) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
        )
        self.value = nn.Linear(hidden_size, 1)
        self.advantage = nn.Linear(hidden_size, n_actions)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder(features)
        value = self.value(encoded)
        advantage = self.advantage(encoded)
        return value + advantage - advantage.mean(dim=-1, keepdim=True)


class DuelingDoubleQRolePolicy:
    """Production adapter from local observations to legally masked DDQN actions."""

    def __init__(self, network: DuelingDoubleQNetwork, role: str, device: torch.device) -> None:
        self.network = network.eval()
        self.role = role
        self.device = device
        self.action_names = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
        self.inference_mode = "argmax"
        self.temperature = None
        # Inverse of the clamped wire scent law; inert unless COPTHIEF_DECODED_SCENT=1. The
        # network is feed-forward but the DECODER is stateful, so reset() is now meaningful.
        self._decoder = None

    def reset(self) -> None:
        """Clear the per-episode scent decoder; the feed-forward network itself has no state."""
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
            local_obs_to_tensor(observation, belief, self._scent_decoder(observation.grid_size)),
            dtype=torch.float32,
            device=self.device,
        ).unsqueeze(0)
        with torch.no_grad():
            q_values = self.network(features)
        mask = torch.tensor(
            [action in legal_actions for action in self.action_names],
            dtype=torch.bool,
            device=self.device,
        ).unsqueeze(0)
        if not bool(mask.any()):
            raise RuntimeError("legal-action mask has no deployable action")
        masked = q_values.masked_fill(~mask, torch.finfo(q_values.dtype).min)
        return self.action_names[int(masked.argmax(dim=-1).item())]


def _load_dueling_policy(manifest_path: Path, entry, role: str) -> DuelingDoubleQRolePolicy:
    from cop_worker.rl.counted_policy import SUPPORTED_GRID_SIZE, CountedPolicyLoadError
    from cop_worker.rl.model_schema import validate_model_file

    if entry.inference_mode != "argmax":
        raise CountedPolicyLoadError("DuelingDoubleDQN requires argmax inference")
    if not entry.artifact:
        raise CountedPolicyLoadError("manifest entry omits model artifact")
    artifact = manifest_path.parent / entry.artifact
    if not artifact.is_file():
        raise CountedPolicyLoadError(f"model artifact not found: {artifact}")
    validate_model_file(str(artifact), entry.sha256)
    checkpoint = torch.load(artifact, map_location="cpu", weights_only=True)
    if checkpoint.get("role") != role:
        raise CountedPolicyLoadError("checkpoint role does not match manifest")
    if checkpoint.get("algorithm") != entry.algorithm:
        raise CountedPolicyLoadError("checkpoint algorithm does not match manifest")
    input_size = int(checkpoint["input_size"])
    if input_size != obs_tensor_shape(SUPPORTED_GRID_SIZE):
        raise CountedPolicyLoadError("checkpoint observation tensor schema is incompatible")
    hidden_size = int(checkpoint["hidden_size"])
    if hidden_size <= 0 or hidden_size > 4096:
        raise CountedPolicyLoadError("checkpoint hidden size is invalid")
    n_actions = int(checkpoint["n_actions"])
    expected_actions = len(COP_ACTIONS if role == "cop" else THIEF_ACTIONS)
    if n_actions != expected_actions:
        raise CountedPolicyLoadError("checkpoint action schema is incompatible")
    network = DuelingDoubleQNetwork(input_size, n_actions, hidden_size)
    network.load_state_dict(checkpoint["state_dict"])
    return DuelingDoubleQRolePolicy(network, role, torch.device("cpu"))
