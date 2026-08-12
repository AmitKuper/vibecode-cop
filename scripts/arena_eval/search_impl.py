"""Policy construction and observation building for the chebyshev arena."""

from __future__ import annotations

from pathlib import Path

import torch

from cop_worker.observation import LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.search_policy import SearchRolePolicy

N = 7


class CheckpointPolicy:
    """Argmax serving wrapper for a train_recurrent checkpoint (.pt)."""

    def __init__(self, path: Path, role: str) -> None:
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        self.net = RecurrentActorCritic(
            int(ckpt["input_size"]), int(ckpt["n_actions"]), int(ckpt["hidden_size"])
        )
        self.net.load_state_dict(ckpt["state_dict"])
        self.net.eval()
        self.role = role
        self.actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
        self.hidden = None

    def reset(self) -> None:
        self.hidden = None

    def select_action(self, obs: LocalObservation, belief, legal: list[str]) -> str:
        features = torch.tensor(
            local_obs_to_tensor(obs, belief, None), dtype=torch.float32
        ).unsqueeze(0)
        with torch.no_grad():
            logits, _value, self.hidden = self.net(features, self.hidden)
        mask = torch.tensor([a in legal for a in self.actions])
        masked = logits.squeeze(0).masked_fill(~mask, float("-inf"))
        return self.actions[int(masked.argmax().item())]


def make_policy(spec: str, role: str, depth: int):
    if spec == "search":
        return SearchRolePolicy(role, depth=depth)
    return CheckpointPolicy(Path(spec), role)


def _obs(own, remaining, barriers, scent_grid, step):
    return LocalObservation(
        own_position=tuple(own),
        own_barriers_remaining=remaining,
        known_barriers=[tuple(b) for b in barriers],
        opponent_scent=scent_grid,
        last_hint="",
        step=step,
        gamelet=1,
        grid_size=N,
    )
