"""Student architectures for barrier distillation.

Two designs test one hypothesis: stall-squeeze walls fire on a HISTORY
pattern (4 turns of stable distance), so a memoryless net should learn wall
*targets* but struggle with wall *timing*, while the GRU can count.
"""

from __future__ import annotations

import torch
from torch import nn

from cop_worker.rl.recurrent_policy import RecurrentActorCritic


class FeedforwardPolicy(nn.Module):
    """Memoryless baseline: same budget class as the GRU student."""

    def __init__(self, input_size: int, n_actions: int, hidden_size: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, n_actions),
        )

    def forward(self, features: torch.Tensor, hidden=None):
        return self.net(features), None, hidden


def make_student(arch: str, input_size: int, n_actions: int):
    """'gru' (deployed architecture) or 'ff' (memoryless ablation)."""
    if arch == "gru":
        return RecurrentActorCritic(input_size, n_actions)
    if arch == "ff":
        return FeedforwardPolicy(input_size, n_actions)
    raise ValueError(f"unknown arch {arch!r}")


def load_student(path: str):
    """Load a checkpoint saved by train.py; returns (network, meta)."""
    blob = torch.load(path, map_location="cpu", weights_only=False)
    net = make_student(blob["arch"], blob["input_size"], blob["n_actions"])
    net.load_state_dict(blob["state_dict"])
    net.eval()
    return net, blob
