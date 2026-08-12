"""Thief-policy loading and book-frame copying for the belief arena."""

from __future__ import annotations

import torch

from cop_worker.rl.action_space import THIEF_ACTIONS
from cop_worker.rl.counted_policy import (
    DuelingDoubleQNetwork,
    DuelingDoubleQRolePolicy,
)
from cop_worker.rl.recurrent_policy import RecurrentActorCritic


class _RecurrentThief:
    """Argmax wrapper for a train_recurrent thief checkpoint."""

    def __init__(self, path: str) -> None:
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        self.net = RecurrentActorCritic(
            int(ckpt["input_size"]), int(ckpt["n_actions"]), int(ckpt["hidden_size"])
        )
        self.net.load_state_dict(ckpt["state_dict"])
        self.net.eval()
        self.hidden = None

    def reset(self) -> None:
        self.hidden = None

    def select_action(self, obs, belief, legal):
        from cop_worker.rl.local_obs_adapter import local_obs_to_tensor

        features = torch.tensor(
            local_obs_to_tensor(obs, belief, None), dtype=torch.float32
        ).unsqueeze(0)
        with torch.no_grad():
            logits, _v, self.hidden = self.net(features, self.hidden)
        mask = torch.tensor([a in legal for a in THIEF_ACTIONS])
        masked = logits.squeeze(0).masked_fill(~mask, float("-inf"))
        return THIEF_ACTIONS[int(masked.argmax().item())]


def _load_thief(spec: str):
    if spec.startswith("ddqn:"):
        ckpt = torch.load(spec[5:], map_location="cpu", weights_only=True)
        net = DuelingDoubleQNetwork(
            int(ckpt["input_size"]), int(ckpt["n_actions"]), int(ckpt["hidden_size"])
        )
        net.load_state_dict(ckpt["state_dict"])
        return DuelingDoubleQRolePolicy(net.eval(), "thief", torch.device("cpu"))
    return _RecurrentThief(spec)


def _book_field(engine_grid: list[list[float]]) -> list[list[float]]:
    return [row[:] for row in engine_grid]
