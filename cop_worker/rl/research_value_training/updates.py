"""Epsilon-greedy action selection and the double-DQN TD update."""

from __future__ import annotations

import random

import numpy as np
import torch
import torch.nn as nn

from cop_worker.rl.research_value_training.networks import DuelingDoubleQNetwork
from cop_worker.rl.research_value_training.replay import ReplayBuffer, ReplayItem


def _masked_epsilon_action(
    network: DuelingDoubleQNetwork,
    features: torch.Tensor,
    mask: torch.Tensor,
    epsilon: float,
    rng: random.Random,
) -> int:
    legal_indices = [index for index, allowed in enumerate(mask) if bool(allowed)]
    if rng.random() < epsilon:
        return rng.choice(legal_indices)
    with torch.no_grad():
        values = network(features.unsqueeze(0)).squeeze(0).masked_fill(~mask, -1e9)
    return int(values.argmax().item())


def _ddqn_update(
    online: DuelingDoubleQNetwork,
    target: DuelingDoubleQNetwork,
    optimizer: torch.optim.Optimizer,
    batch: list[ReplayItem],
    gamma: float,
) -> float:
    observations = torch.tensor(np.stack([item.observation for item in batch]))
    actions = torch.tensor([item.action for item in batch], dtype=torch.long)
    rewards = torch.tensor([item.reward for item in batch], dtype=torch.float32)
    next_observations = torch.tensor(np.stack([item.next_observation for item in batch]))
    done = torch.tensor([item.done for item in batch], dtype=torch.float32)
    next_mask = torch.tensor(np.stack([item.next_mask for item in batch]), dtype=torch.bool)
    predicted = online(observations).gather(1, actions.unsqueeze(1)).squeeze(1)
    with torch.no_grad():
        online_next = online(next_observations).masked_fill(~next_mask, -1e9)
        next_actions = online_next.argmax(dim=1)
        target_next = target(next_observations).gather(1, next_actions.unsqueeze(1)).squeeze(1)
        expected = rewards + gamma * target_next * (1.0 - done)
    loss = nn.functional.smooth_l1_loss(predicted, expected)
    optimizer.zero_grad()
    loss.backward()
    nn.utils.clip_grad_norm_(online.parameters(), 10.0)
    optimizer.step()
    return float(loss.item())


def _remember(
    replay: ReplayBuffer,
    features: torch.Tensor,
    action_index: int,
    reward: float,
    next_features: torch.Tensor,
    terminal: bool,
    next_mask: torch.Tensor,
) -> None:
    replay.add(
        ReplayItem(
            features.numpy().astype(np.float32),
            action_index,
            reward,
            next_features.numpy().astype(np.float32),
            terminal,
            next_mask.numpy(),
        )
    )
