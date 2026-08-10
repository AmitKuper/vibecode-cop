"""Dueling Double-DQN training loop."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.rl.research_value_training.ddqn_artifact import _finalize_ddqn
from cop_worker.rl.research_value_training.networks import (
    DQNResearchPolicy,
    DuelingDoubleQNetwork,
    _actions,
)
from cop_worker.rl.research_value_training.replay import ReplayBuffer
from cop_worker.rl.research_value_training.shaping import (
    _default_population,
    _frozen_opponent,
    _local_shaping,
    _terminal_reward,
    _update_beliefs,
)
from cop_worker.rl.research_value_training.updates import (
    _ddqn_update,
    _masked_epsilon_action,
    _remember,
)
from cop_worker.rl.train_recurrent import _initial_state, _legal, _observation
from cop_worker.scent import make_scent_fields


def train_ddqn(
    role: str,
    episodes: int,
    seed: int,
    incumbent_path: Path,
    output: Path,
    hidden_size: int = 256,
    fixed_start_probability: float = 1.0,
) -> tuple[DQNResearchPolicy, dict]:
    """Train a best response against a frozen PSRO-style opponent population."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    rng = random.Random(seed)
    input_size = 4 * 7 * 7 + 5
    actions = _actions(role)
    online = DuelingDoubleQNetwork(input_size, len(actions), hidden_size)
    target = DuelingDoubleQNetwork(input_size, len(actions), hidden_size)
    target.load_state_dict(online.state_dict())
    optimizer = torch.optim.Adam(online.parameters(), lr=3e-4)
    replay = ReplayBuffer(100_000)
    population_names = _default_population(role)
    population = {
        family: _frozen_opponent(role, family, incumbent_path) for family in set(population_names)
    }
    wins: list[int] = []
    lengths: list[int] = []
    losses: list[float] = []
    environment_steps = 0
    for episode in range(episodes):
        family = population_names[episode % len(population_names)]
        opponent = population[family]
        random_start = rng.random() > fixed_start_probability
        gamelet = (episode % 6) + 1
        state = _initial_state(rng, random_start=random_start, grid_size=7)
        scent = make_scent_fields(7)
        cop_belief = BeliefEngine(7, "cop")
        thief_belief = BeliefEngine(7, "thief")
        opponent.reset(seed + episode * 97)
        while state.turn < 35:
            belief = cop_belief if role == "cop" else thief_belief
            legal = _legal(state, role)
            features, mask = _observation(state, role, scent, belief, legal, gamelet)
            progress = environment_steps / max(episodes * 24, 1)
            epsilon = max(0.05, 1.0 - 0.95 * progress)
            action_index = _masked_epsilon_action(online, features, mask, epsilon, rng)
            action = actions[action_index]
            opponent_belief = thief_belief if role == "cop" else cop_belief
            opponent_action = opponent.act(state, scent, opponent_belief, rng, gamelet)
            cop_action, thief_action = (
                (action, opponent_action) if role == "cop" else (opponent_action, action)
            )
            before_state = state
            before_belief = belief
            result = apply_joint_action(state, cop_action, thief_action)
            state = result.new_state
            scent, cop_belief, thief_belief = _update_beliefs(
                state, scent, cop_belief, thief_belief
            )
            next_belief = cop_belief if role == "cop" else thief_belief
            terminal = result.outcome.value != "ongoing"
            if terminal:
                winner = "cop" if result.outcome.value == "cop_win" else "thief"
                reward = _terminal_reward(winner, role)
                next_features = features
                next_mask = mask
            else:
                reward = _local_shaping(role, before_state, state, before_belief, next_belief)
                next_legal = _legal(state, role)
                next_features, next_mask = _observation(
                    state,
                    role,
                    scent,
                    next_belief,
                    next_legal,
                    gamelet,
                )
            _remember(replay, features, action_index, reward, next_features, terminal, next_mask)
            environment_steps += 1
            if len(replay) >= 1_024 and environment_steps % 2 == 0:
                losses.append(
                    _ddqn_update(
                        online,
                        target,
                        optimizer,
                        replay.sample(rng, 128),
                        gamma=0.99,
                    )
                )
            if environment_steps % 1_000 == 0:
                target.load_state_dict(online.state_dict())
            if terminal:
                wins.append(int(winner == role))
                lengths.append(state.turn)
                break
    target.load_state_dict(online.state_dict())
    metrics = _finalize_ddqn(
        online,
        role,
        episodes,
        seed,
        hidden_size,
        input_size,
        len(actions),
        fixed_start_probability,
        list(population_names),
        environment_steps,
        wins,
        lengths,
        losses,
        output,
    )
    return DQNResearchPolicy(online.eval(), role), metrics
