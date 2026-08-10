"""Tabular Q-learning policy and training loop."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.rl.research_value_training.networks import _actions
from cop_worker.rl.research_value_training.qtable_policy import TabularResearchPolicy, _q_key
from cop_worker.rl.research_value_training.shaping import (
    _default_population,
    _frozen_opponent,
    _local_shaping,
    _terminal_reward,
    _update_beliefs,
)
from cop_worker.rl.train_recurrent import _initial_state, _legal
from cop_worker.scent import make_scent_fields


def train_q_table(
    role: str,
    episodes: int,
    seed: int,
    incumbent_path: Path,
    output: Path,
) -> tuple[TabularResearchPolicy, dict]:
    rng = random.Random(seed)
    actions = _actions(role)
    q_values: dict[tuple[int, ...], np.ndarray] = {}
    visits: dict[tuple[int, ...], int] = {}
    population_names = _default_population(role)
    population = {
        family: _frozen_opponent(role, family, incumbent_path) for family in set(population_names)
    }
    wins: list[int] = []
    for episode in range(episodes):
        family = population_names[episode % len(population_names)]
        opponent = population[family]
        gamelet = (episode % 6) + 1
        state = _initial_state(rng, random_start=False, grid_size=7)
        scent = make_scent_fields(7)
        cop_belief = BeliefEngine(7, "cop")
        thief_belief = BeliefEngine(7, "thief")
        opponent.reset(seed + episode * 97)
        while state.turn < 35:
            belief = cop_belief if role == "cop" else thief_belief
            key = _q_key(state, role, belief)
            values = q_values.setdefault(key, np.zeros(len(actions), dtype=np.float32))
            legal = _legal(state, role)
            epsilon = max(0.03, 0.9 * (1.0 - episode / max(episodes, 1)))
            if rng.random() < epsilon:
                action = rng.choice(legal)
            else:
                action = max(
                    legal,
                    key=lambda item: (float(values[actions.index(item)]), -actions.index(item)),
                )
            action_index = actions.index(action)
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
                bootstrap = 0.0
            else:
                reward = _local_shaping(role, before_state, state, before_belief, next_belief)
                next_key = _q_key(state, role, next_belief)
                next_values = q_values.setdefault(
                    next_key, np.zeros(len(actions), dtype=np.float32)
                )
                next_legal = _legal(state, role)
                bootstrap = max(float(next_values[actions.index(item)]) for item in next_legal)
            visits[key] = visits.get(key, 0) + 1
            alpha = max(0.05, 1.0 / math.sqrt(visits[key]))
            target = reward + 0.99 * bootstrap
            values[action_index] += alpha * (target - float(values[action_index]))
            if terminal:
                wins.append(int(winner == role))
                break
    serializable = {"|".join(map(str, key)): value.tolist() for key, value in q_values.items()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "role": role,
                "algorithm": "TabularQ",
                "episodes": episodes,
                "seed": seed,
                "opponent_population": list(population_names),
                "q_values": serializable,
            }
        )
    )
    metrics = {
        "algorithm": "TabularQ",
        "role": role,
        "episodes": episodes,
        "states": len(q_values),
        "training_win_rate_last_500": sum(wins[-500:]) / max(len(wins[-500:]), 1),
        "opponent_population": list(population_names),
    }
    return TabularResearchPolicy(q_values, role), metrics
