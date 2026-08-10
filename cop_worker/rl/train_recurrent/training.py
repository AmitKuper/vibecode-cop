"""Recurrent A2C training loop with expert mixing and imitation regularizer."""

from __future__ import annotations

import random

import numpy as np
import torch

import cop_worker.rl.train_recurrent as _pkg
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import obs_tensor_shape
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.train_recurrent.schedules import (
    COP_TRAINING_SCHEDULE,
    THIEF_TRAINING_SCHEDULE,
)


def train(
    role: str,
    episodes: int,
    seed: int,
    hidden_size: int,
    historical_policy,
    resume_checkpoint: dict | None = None,
    resume_learning_rate: float = 3e-4,
    resume_expert_probability: float = 0.0,
    resume_imitation_weight: float = 0.0,
    training_schedule: tuple[str, ...] | None = None,
    grid_size: int = 7,
    fixed_start_fraction: float = 0.0,
) -> RecurrentActorCritic:
    torch.manual_seed(seed)
    np.random.seed(seed)
    rng = random.Random(seed)
    if resume_checkpoint is None:
        network = RecurrentActorCritic(
            obs_tensor_shape(grid_size),
            len(COP_ACTIONS if role == "cop" else THIEF_ACTIONS),
            hidden_size,
        )
        _pkg._pretrain_imitation(network, role, rng, historical_policy, grid_size=grid_size)
    else:
        if resume_checkpoint.get("role") != role:
            raise RuntimeError("resume checkpoint role does not match training role")
        network = RecurrentActorCritic(
            int(resume_checkpoint["input_size"]),
            int(resume_checkpoint["n_actions"]),
            int(resume_checkpoint["hidden_size"]),
        )
        network.load_state_dict(resume_checkpoint["state_dict"])
    learning_rate = resume_learning_rate if resume_checkpoint is not None else 3e-4
    optimizer = torch.optim.Adam(network.parameters(), lr=learning_rate)
    for episode in range(episodes):
        schedule = training_schedule or (
            THIEF_TRAINING_SCHEDULE if role == "thief" else COP_TRAINING_SCHEDULE
        )
        family = schedule[episode % len(schedule)]
        progress = episode / max(episodes - 1, 1)
        if resume_checkpoint is not None:
            expert_probability = resume_expert_probability
            imitation_weight = resume_imitation_weight
        elif role == "thief":
            expert_probability = max(0.0, 0.60 * (1.0 - 2.0 * progress))
            imitation_weight = max(0.0, 1.0 - 1.5 * progress)
        else:
            expert_probability = max(0.10, 0.80 * (1.0 - progress))
            imitation_weight = 1.0
        # Match starts are CONTRACTUAL (cop_start/thief_start are signed terms), so a
        # fraction of episodes may pin the opening distribution the match actually
        # visits; the rest stay random for mid-game state coverage. Default 0.0
        # preserves the historical fully-random recipe.
        trajectory, _winner, _turns = _pkg._run_episode(
            network,
            role,
            family,
            rng,
            training=True,
            random_start=rng.random() >= fixed_start_fraction,
            expert_probability=expert_probability,
            historical_policy=historical_policy,
            grid_size=grid_size,
        )
        returns = []
        total = 0.0
        for *_unused, reward in reversed(trajectory):
            total = reward + 0.99 * total
            returns.append(total)
        returns.reverse()
        returns_tensor = torch.tensor(returns, dtype=torch.float32)
        if len(returns_tensor) > 1:
            returns_tensor = (returns_tensor - returns_tensor.mean()) / (
                returns_tensor.std() + 1e-6
            )
        losses = []
        for (
            log_prob,
            policy_selected,
            value,
            entropy,
            expert_log_prob,
            _reward,
        ), target in zip(trajectory, returns_tensor, strict=True):
            advantage = target - value
            actor_loss = -log_prob * advantage.detach() if policy_selected else 0.0
            losses.append(
                actor_loss
                + 0.5 * advantage**2
                - 0.01 * entropy
                - imitation_weight * expert_log_prob
            )
        optimizer.zero_grad()
        torch.stack(losses).mean().backward()
        torch.nn.utils.clip_grad_norm_(network.parameters(), 0.5)
        optimizer.step()
    return network.eval()
