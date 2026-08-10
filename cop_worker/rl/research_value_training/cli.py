"""CLI entry: train the value-based research candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from cop_worker.rl.research_evaluation import (
    RecurrentResearchPolicy,
    ResearchPolicy,
    evaluate_crossplay,
    evaluate_families,
    load_recurrent_network,
)
from cop_worker.rl.research_value_training.ddqn import train_ddqn
from cop_worker.rl.research_value_training.networks import load_dqn_policy
from cop_worker.rl.research_value_training.qtable import train_q_table


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
    incumbent_metadata = torch.load(args.incumbent_opponent, map_location="cpu", weights_only=True)
    if incumbent_metadata.get("algorithm") == "DuelingDoubleDQN":
        incumbent: ResearchPolicy = load_dqn_policy(args.incumbent_opponent, opponent_role)
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
