"""Counted-mode recurrent actor-critic policy over local-only observations."""

from __future__ import annotations

import secrets

import torch
import torch.nn as nn

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor


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
        # is reset per episode. Enabled per-policy when the manifest records
        # decoded_scent=true (the env flag remains a training-side override).
        self._decoder = None
        self.use_decoded_scent = False

    def reset(self) -> None:
        self._hidden = None
        if self._decoder is not None:
            self._decoder.reset()

    def _scent_decoder(self, grid_size: int):
        from cop_worker.rl.obs_mode import decoded_scent_enabled
        from cop_worker.scent_decoder import EmitterDecoder

        if not (self.use_decoded_scent or decoded_scent_enabled()):
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


# Loader lives in ``cop_worker.rl.recurrent_loader`` (needs the classes above, so
# this import must stay at the bottom); re-exported here for the public API.
from cop_worker.rl.recurrent_loader import file_sha256, load_recurrent_policy  # noqa: E402

__all__ = [
    "RecurrentActorCritic",
    "RecurrentPolicyLoadError",
    "RecurrentRolePolicy",
    "file_sha256",
    "load_recurrent_policy",
]
