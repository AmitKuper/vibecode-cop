"""Dueling Double-DQN network, serving policy, and artifact loader."""

from __future__ import annotations

import random
from pathlib import Path

import torch
import torch.nn as nn

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.train_recurrent import _legal, _observation
from cop_worker.scent import ScentFields


def _actions(role: str) -> list[str]:
    return COP_ACTIONS if role == "cop" else THIEF_ACTIONS


class DuelingDoubleQNetwork(nn.Module):
    """Dueling value/advantage network for local flat observations."""

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


class DQNResearchPolicy:
    """Inference adapter for a local-observation Q network."""

    def __init__(self, network: DuelingDoubleQNetwork, role: str) -> None:
        self.network = network.eval()
        self.role = role

    def reset(self, seed: int) -> None:
        del seed

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str:
        del rng
        legal = _legal(state, self.role)
        features, mask = _observation(state, self.role, scent, belief, legal, gamelet)
        with torch.no_grad():
            values = self.network(features.unsqueeze(0)).squeeze(0)
        values = values.masked_fill(~mask, -1e9)
        return _actions(self.role)[int(values.argmax().item())]


def load_dqn_policy(path: str | Path, expected_role: str) -> DQNResearchPolicy:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint.get("algorithm") != "DuelingDoubleDQN":
        raise ValueError(f"{path} is not a DuelingDoubleDQN artifact")
    if checkpoint.get("role") != expected_role:
        raise ValueError(f"{path} is not a {expected_role} artifact")
    network = DuelingDoubleQNetwork(
        int(checkpoint["input_size"]),
        int(checkpoint["n_actions"]),
        int(checkpoint["hidden_size"]),
    )
    network.load_state_dict(checkpoint["state_dict"])
    return DQNResearchPolicy(network, expected_role)
