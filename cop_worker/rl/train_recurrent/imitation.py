"""Behaviour-cloning warm start from the local-only belief expert."""

from __future__ import annotations

import random

import torch

import cop_worker.rl.train_recurrent as _pkg
from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.train_recurrent.episode_steps import _advance_beliefs
from cop_worker.rl.train_recurrent.expert import _belief_expert_action
from cop_worker.rl.train_recurrent.observation import _observation
from cop_worker.rl.train_recurrent.schedules import FAMILIES
from cop_worker.rl.train_recurrent.sim import _legal
from cop_worker.scent import make_scent_fields


def _collect_demonstrations(
    role: str, rng: random.Random, episodes: int, historical_policy, grid_size: int = 7
) -> tuple[torch.Tensor, torch.Tensor]:
    """Collect strictly local-observation labels from the belief expert."""
    features: list[torch.Tensor] = []
    labels: list[int] = []
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    opponent_role = "thief" if role == "cop" else "cop"
    demo_families = [
        family
        for family in FAMILIES
        if family != "historical_checkpoint" or historical_policy is not None
    ]
    for episode in range(episodes):
        family = demo_families[episode % len(demo_families)]
        state = _pkg._initial_state(rng, random_start=True, grid_size=grid_size)
        scent = make_scent_fields(grid_size)
        belief = BeliefEngine(grid_size, role)
        opponent_belief = BeliefEngine(grid_size, opponent_role)
        while state.turn < 35:
            legal = _legal(state, role)
            observation, _mask = _observation(
                state, role, scent, belief, legal, (state.turn % 6) + 1
            )
            own_position = state.cop_position if role == "cop" else state.thief_position
            action = _belief_expert_action(own_position, role, belief, legal)
            features.append(observation)
            labels.append(actions.index(action))
            opponent_scent = (
                scent.thief_observation_scent()
                if opponent_role == "thief"
                else scent.cop_observation_scent()
            )
            opponent = _pkg._opponent_action(
                state,
                opponent_role,
                family,
                rng,
                historical_policy=historical_policy,
                opponent_scent=opponent_scent,
                opponent_belief=opponent_belief,
            )
            cop_action, thief_action = (action, opponent) if role == "cop" else (opponent, action)
            result = apply_joint_action(state, cop_action, thief_action)
            state = result.new_state
            scent, belief, opponent_belief = _advance_beliefs(
                scent, state, role, opponent_role, belief, opponent_belief
            )
            if result.outcome.value != "ongoing":
                break
    return torch.stack(features), torch.tensor(labels, dtype=torch.long)


def _pretrain_imitation(
    network: RecurrentActorCritic,
    role: str,
    rng: random.Random,
    historical_policy,
    demonstration_episodes: int = 240,
    updates: int = 600,
    grid_size: int = 7,
) -> None:
    """Warm-start the recurrent network on local-only expert demonstrations."""
    features, labels = _pkg._collect_demonstrations(
        role, rng, demonstration_episodes, historical_policy, grid_size
    )
    optimizer = torch.optim.Adam(network.parameters(), lr=1e-3)
    network.train()
    batch_size = min(128, len(labels))
    for _ in range(updates):
        indices = torch.randint(0, len(labels), (batch_size,))
        logits, _value, _hidden = network(features[indices], None)
        loss = torch.nn.functional.cross_entropy(logits, labels[indices])
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(network.parameters(), 0.5)
        optimizer.step()
