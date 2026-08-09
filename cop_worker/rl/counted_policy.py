"""Checksum-verified counted inference for supported RL architectures."""

from __future__ import annotations

from pathlib import Path

import torch
import torch.nn as nn

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape

SUPPORTED_GRID_SIZE = 7


class CountedPolicyLoadError(RuntimeError):
    """Raised when a manifest-selected counted policy cannot be loaded safely."""


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
            local_obs_to_tensor(
                observation, belief, self._scent_decoder(observation.grid_size)
            ),
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


def _guard_serving_obs_mode(entry, role: str) -> None:
    """Refuse to serve a policy whose SERVING observation a stray env flag would alter.

    Two switches change what the net reads at inference time (not merely in training):
    ``COPTHIEF_DECODED_SCENT`` (the decoder inverts the scent channels inside
    ``local_obs_to_tensor``) and ``COPTHIEF_SCENT_MODEL`` (which physics our emission
    and the training fields ran). A live value that contradicts what the manifest
    records for the artifact means the net reads inputs it never trained on — the
    exact silent-regression shape this project has shipped before. Manifests written
    before the switches existed read as book-model / decoder-off.
    """
    from cop_worker.rl.obs_mode import decoded_scent_enabled, scent_model

    recorded = dict(getattr(entry, "obs_mode", None) or {})
    want_decoded = bool(recorded.get("decoded_scent", False))
    if decoded_scent_enabled() != want_decoded:
        raise CountedPolicyLoadError(
            f"COPTHIEF_DECODED_SCENT={'1' if decoded_scent_enabled() else 'off'} but the "
            f"{role} manifest entry records decoded_scent={want_decoded} — a stray env "
            f"flag would silently change the serving observation; unset it or promote a "
            f"matching artifact"
        )
    want_model = recorded.get("scent_model", "multiplicative_book_v1")
    if scent_model() != want_model:
        raise CountedPolicyLoadError(
            f"COPTHIEF_SCENT_MODEL resolves to {scent_model()!r} but the {role} manifest "
            f"entry records scent_model={want_model!r} — the net would read a field it "
            f"never trained on; align the locked model and the promoted artifact"
        )


def load_counted_policy(manifest_path: str | Path, role: str):
    """Load the manifest-selected recurrent or dueling-DDQN counted policy."""
    from cop_worker.rl.model_schema import load_manifest

    manifest_path = Path(manifest_path)
    entries = load_manifest(str(manifest_path))
    if role not in entries:
        raise CountedPolicyLoadError(f"manifest has no {role!r} policy")
    entry = entries[role]
    compatible, reason = entry.is_compatible(role, SUPPORTED_GRID_SIZE)
    if not compatible:
        raise CountedPolicyLoadError(reason)
    _guard_serving_obs_mode(entry, role)
    if entry.algorithm == "RecurrentA2C-GRU":
        from cop_worker.rl.recurrent_policy import load_recurrent_policy

        return load_recurrent_policy(manifest_path, role)
    if entry.algorithm == "DuelingDoubleDQN":
        return _load_dueling_policy(manifest_path, entry, role)
    raise CountedPolicyLoadError(f"unsupported counted algorithm {entry.algorithm!r}")
