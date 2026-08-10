"""Single-episode rollout shared by training and the held-out tournament."""

from __future__ import annotations

import random
import time

import torch

import cop_worker.rl.train_recurrent as _pkg
from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.train_recurrent.episode_steps import (
    _ablate_features,
    _advance_beliefs,
    _note_barrier_metric,
    _note_choice_metrics,
    _note_decision_metrics,
    _step_reward,
)
from cop_worker.rl.train_recurrent.expert import _belief_expert_action
from cop_worker.rl.train_recurrent.observation import _observation
from cop_worker.rl.train_recurrent.sim import _distance, _legal
from cop_worker.scent import make_scent_fields


def _run_episode(
    network: RecurrentActorCritic,
    role: str,
    family: str,
    rng: random.Random,
    training: bool,
    random_start: bool,
    expert_probability: float = 0.0,
    historical_policy=None,
    evaluation_temperature: float | None = None,
    force_expert_actor: bool = False,
    latency_samples: list[float] | None = None,
    episode_metrics: dict[str, int] | None = None,
    feature_mode: str = "full",
    recurrent_enabled: bool = True,
    legal_mask_enabled: bool = True,
    risk_mask_enabled: bool = False,
    barrier_actions_enabled: bool = True,
    grid_size: int = 7,
) -> tuple[list, str, int]:
    state = _pkg._initial_state(rng, random_start, grid_size)
    scent = make_scent_fields(grid_size)
    belief = BeliefEngine(grid_size, role)
    opponent_role = "thief" if role == "cop" else "cop"
    opponent_belief = BeliefEngine(grid_size, opponent_role)
    hidden = None
    trajectory = []
    winner = "thief"
    while state.turn < 35:
        legal = _legal(state, role)
        actor_legal = (
            [action for action in legal if not action.startswith("PLACE_")]
            if role == "cop" and not barrier_actions_enabled
            else legal
        )
        features, mask = _observation(
            state,
            role,
            scent,
            belief,
            actor_legal,
            (state.turn % 6) + 1,
            risk_mask_enabled,
        )
        _ablate_features(features, feature_mode, state.grid_size * state.grid_size)
        if not legal_mask_enabled:
            mask = torch.ones_like(mask)
        _note_choice_metrics(
            episode_metrics, legal, mask, COP_ACTIONS if role == "cop" else THIEF_ACTIONS
        )
        inference_started = time.perf_counter()
        logits, value, hidden = network(
            features.unsqueeze(0), hidden if recurrent_enabled else None
        )
        if latency_samples is not None and not force_expert_actor:
            latency_samples.append((time.perf_counter() - inference_started) * 1000)
        masked = logits.squeeze(0).masked_fill(~mask, -1e9)
        dist = torch.distributions.Categorical(logits=masked)
        if training:
            policy_index = dist.sample()
        elif evaluation_temperature is not None:
            policy_index = torch.distributions.Categorical(
                logits=masked / evaluation_temperature
            ).sample()
        else:
            policy_index = masked.argmax()
        own_position = state.cop_position if role == "cop" else state.thief_position
        expert_action = _belief_expert_action(own_position, role, belief, legal)
        expert_index = (COP_ACTIONS if role == "cop" else THIEF_ACTIONS).index(expert_action)
        use_expert = force_expert_actor or (training and rng.random() < expert_probability)
        action_index = torch.tensor(expert_index) if use_expert else policy_index
        action = (COP_ACTIONS if role == "cop" else THIEF_ACTIONS)[int(action_index)]
        _note_decision_metrics(episode_metrics, action, legal)
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
        _note_barrier_metric(episode_metrics, cop_action)
        previous_distance = _distance(state)
        previous_barriers = list(state.barriers)
        result = apply_joint_action(state, cop_action, thief_action)
        state = result.new_state
        if not recurrent_enabled:
            hidden = None
        terminal, step_winner, reward = _step_reward(
            role,
            result.outcome.value,
            previous_distance,
            _distance(state),
            previous_barriers,
            state,
            belief,
        )
        if step_winner is not None:
            winner = step_winner
        trajectory.append(
            (
                dist.log_prob(action_index),
                not use_expert,
                value.squeeze(),
                dist.entropy(),
                dist.log_prob(torch.tensor(expert_index)),
                reward,
            )
        )
        scent, belief, opponent_belief = _advance_beliefs(
            scent, state, role, opponent_role, belief, opponent_belief
        )
        if terminal:
            break
    return trajectory, winner, state.turn
