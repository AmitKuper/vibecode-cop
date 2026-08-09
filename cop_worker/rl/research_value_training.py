"""Tabular Q-learning and dueling Double-DQN research on canonical physics.

The trainers use only ``LocalObservation`` features and Bayesian belief.  Their
opponents are frozen policies sampled from a population, avoiding the moving
target and role-collapse problem of simultaneous independent self-play.
Artifacts produced here are research candidates and are not installed into the
counted manifest automatically.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.domain.types import DomainState
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.research_evaluation import (
    RecurrentResearchPolicy,
    ResearchPolicy,
    ScriptedResearchPolicy,
    evaluate_crossplay,
    evaluate_families,
    load_recurrent_network,
)
from cop_worker.rl.train_recurrent import _initial_state, _legal, _observation
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


@dataclass(frozen=True)
class ReplayItem:
    observation: np.ndarray
    action: int
    reward: float
    next_observation: np.ndarray
    done: bool
    next_mask: np.ndarray


class ReplayBuffer:
    def __init__(self, capacity: int) -> None:
        self.items: deque[ReplayItem] = deque(maxlen=capacity)

    def add(self, item: ReplayItem) -> None:
        self.items.append(item)

    def sample(self, rng: random.Random, count: int) -> list[ReplayItem]:
        return rng.sample(self.items, count)

    def __len__(self) -> int:
        return len(self.items)


def _expected_distance(
    own: tuple[int, int], belief: BeliefEngine, grid_size: int
) -> float:
    probability = belief.belief.prob
    return sum(
        float(probability[y, x]) * (abs(own[0] - x) + abs(own[1] - y))
        for y in range(grid_size)
        for x in range(grid_size)
    )


def _local_shaping(
    role: str,
    before_state: DomainState,
    after_state: DomainState,
    before_belief: BeliefEngine,
    after_belief: BeliefEngine,
) -> float:
    before_own = (
        before_state.cop_position if role == "cop" else before_state.thief_position
    )
    after_own = after_state.cop_position if role == "cop" else after_state.thief_position
    before_distance = _expected_distance(before_own, before_belief, before_state.grid_size)
    after_distance = _expected_distance(after_own, after_belief, after_state.grid_size)
    progress = before_distance - after_distance
    reward = 0.035 * progress if role == "cop" else -0.035 * progress
    return reward - 0.002 if role == "cop" else reward + 0.002


def _update_beliefs(
    state: DomainState,
    scent: ScentFields,
    cop_belief: BeliefEngine,
    thief_belief: BeliefEngine,
) -> tuple[ScentFields, BeliefEngine, BeliefEngine]:
    scent = scent.update(state.cop_position, state.thief_position)
    barriers = [tuple(item) for item in state.barriers]
    cop_belief = cop_belief.predict(barriers).observe_scent(
        scent.cop_observation_scent(), barriers
    )
    thief_belief = thief_belief.predict(barriers).observe_scent(
        scent.thief_observation_scent(), barriers
    )
    return scent, cop_belief, thief_belief


def _frozen_opponent(
    role: str,
    family: str,
    incumbent_path: Path,
) -> ResearchPolicy:
    opponent_role = "thief" if role == "cop" else "cop"
    if family == "historical_checkpoint":
        metadata = torch.load(incumbent_path, map_location="cpu", weights_only=True)
        if metadata.get("algorithm") == "DuelingDoubleDQN":
            return load_dqn_policy(incumbent_path, opponent_role)
        return RecurrentResearchPolicy(
            load_recurrent_network(incumbent_path, opponent_role),
            opponent_role,
            temperature=0.5 if opponent_role == "thief" else None,
        )
    return ScriptedResearchPolicy(opponent_role, family)


def _default_population(role: str) -> tuple[str, ...]:
    if role == "cop":
        return (
            "historical_checkpoint",
            "historical_checkpoint",
            "historical_checkpoint",
            "anti_loop",
            "targeted_exploit",
            "scent_following",
            "local_adversarial_ensemble",
        )
    return (
        "anti_loop",
        "anti_loop",
        "anti_loop",
        "historical_checkpoint",
        "historical_checkpoint",
        "scent_following",
        "corridor_cutting",
    )


def _terminal_reward(winner: str, role: str) -> float:
    return 1.0 if winner == role else -1.0


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
        family: _frozen_opponent(role, family, incumbent_path)
        for family in set(population_names)
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
        scent = ScentFields.zeros(7)
        cop_belief = BeliefEngine(7, "cop")
        thief_belief = BeliefEngine(7, "thief")
        opponent.reset(seed + episode * 97)
        while state.turn < 35:
            belief = cop_belief if role == "cop" else thief_belief
            legal = _legal(state, role)
            features, mask = _observation(
                state, role, scent, belief, legal, gamelet
            )
            progress = environment_steps / max(episodes * 24, 1)
            epsilon = max(0.05, 1.0 - 0.95 * progress)
            action_index = _masked_epsilon_action(online, features, mask, epsilon, rng)
            action = actions[action_index]
            opponent_belief = thief_belief if role == "cop" else cop_belief
            opponent_action = opponent.act(
                state, scent, opponent_belief, rng, gamelet
            )
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
                reward = _local_shaping(
                    role, before_state, state, before_belief, next_belief
                )
                next_legal = _legal(state, role)
                next_features, next_mask = _observation(
                    state,
                    role,
                    scent,
                    next_belief,
                    next_legal,
                    gamelet,
                )
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
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "role": role,
            "algorithm": "DuelingDoubleDQN",
            "input_size": input_size,
            "n_actions": len(actions),
            "hidden_size": hidden_size,
            "training_episodes": episodes,
            "environment_steps": environment_steps,
            "seed": seed,
            "fixed_start_probability": fixed_start_probability,
            "opponent_population": list(population_names),
            "state_dict": online.state_dict(),
        },
        output,
    )
    metrics = {
        "algorithm": "DuelingDoubleDQN",
        "role": role,
        "episodes": episodes,
        "environment_steps": environment_steps,
        "training_win_rate_last_500": sum(wins[-500:]) / max(len(wins[-500:]), 1),
        "average_length_last_500": sum(lengths[-500:]) / max(len(lengths[-500:]), 1),
        "mean_loss_last_1000": sum(losses[-1000:]) / max(len(losses[-1000:]), 1),
        "opponent_population": list(population_names),
    }
    return DQNResearchPolicy(online.eval(), role), metrics


def _q_key(state: DomainState, role: str, belief: BeliefEngine) -> tuple[int, ...]:
    own = state.cop_position if role == "cop" else state.thief_position
    target_index = int(belief.belief.prob.argmax())
    target = (target_index % state.grid_size, target_index // state.grid_size)
    barriers = set(state.barriers)
    adjacency = sum(
        1 << index
        for index, (dx, dy) in enumerate(((0, -1), (0, 1), (1, 0), (-1, 0)))
        if (own[0] + dx, own[1] + dy) in barriers
        or not (0 <= own[0] + dx < 7 and 0 <= own[1] + dy < 7)
    )
    return (
        own[0],
        own[1],
        target[0],
        target[1],
        min(state.turn // 5, 6),
        min(int(belief.belief.confidence * 10), 9),
        adjacency,
        min(state.cop_barriers_remaining // 3, 4) if role == "cop" else 0,
    )


class TabularResearchPolicy:
    def __init__(self, q_values: dict[tuple[int, ...], np.ndarray], role: str) -> None:
        self.q_values = q_values
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
        del scent, rng, gamelet
        actions = _actions(self.role)
        legal = _legal(state, self.role)
        values = self.q_values.get(_q_key(state, self.role, belief), np.zeros(len(actions)))
        return max(
            legal,
            key=lambda action: (
                float(values[actions.index(action)]),
                -actions.index(action),
            ),
        )


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
        family: _frozen_opponent(role, family, incumbent_path)
        for family in set(population_names)
    }
    wins: list[int] = []
    for episode in range(episodes):
        family = population_names[episode % len(population_names)]
        opponent = population[family]
        gamelet = (episode % 6) + 1
        state = _initial_state(rng, random_start=False, grid_size=7)
        scent = ScentFields.zeros(7)
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
            opponent_action = opponent.act(
                state, scent, opponent_belief, rng, gamelet
            )
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
                reward = _local_shaping(
                    role, before_state, state, before_belief, next_belief
                )
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--algorithm", choices=("ddqn", "qtable"), required=True)
    parser.add_argument("--role", choices=("cop", "thief"), required=True)
    parser.add_argument("--episodes", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument("--incumbent-opponent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    args = parser.parse_args()
    if args.algorithm == "ddqn":
        policy, metrics = train_ddqn(
            args.role,
            args.episodes,
            args.seed,
            args.incumbent_opponent,
            args.output,
        )
    else:
        policy, metrics = train_q_table(
            args.role,
            args.episodes,
            args.seed,
            args.incumbent_opponent,
            args.output,
        )
    opponent_role = "thief" if args.role == "cop" else "cop"
    incumbent_metadata = torch.load(
        args.incumbent_opponent, map_location="cpu", weights_only=True
    )
    if incumbent_metadata.get("algorithm") == "DuelingDoubleDQN":
        incumbent: ResearchPolicy = load_dqn_policy(
            args.incumbent_opponent, opponent_role
        )
    else:
        incumbent = RecurrentResearchPolicy(
            load_recurrent_network(args.incumbent_opponent, opponent_role),
            opponent_role,
            temperature=0.5 if opponent_role == "thief" else None,
        )
    cop, thief = (policy, incumbent) if args.role == "cop" else (incumbent, policy)
    metrics["fixed_start_crossplay"] = evaluate_crossplay(
        cop, thief, series=10, seed=args.seed + 1_000_000, random_start=False
    )
    metrics["random_start_crossplay"] = evaluate_crossplay(
        cop, thief, series=10, seed=args.seed + 2_000_000, random_start=True
    )
    metrics["fixed_start_families"] = evaluate_families(
        policy,
        args.role,
        incumbent,
        series_per_family=1,
        seed=args.seed + 3_000_000,
        random_start=False,
    )
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
