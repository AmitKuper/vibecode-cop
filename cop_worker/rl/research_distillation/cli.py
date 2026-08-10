"""CLI entry: distil teachers and evaluate the student."""

from __future__ import annotations

import json

import torch

from cop_worker.rl.recurrent_policy import file_sha256
from cop_worker.rl.research_distillation.cli_args import _build_parser
from cop_worker.rl.research_distillation.distill import train_sequence_distillation
from cop_worker.rl.research_distillation.population import _population
from cop_worker.rl.research_distillation.teacher import collect_teacher_sequences
from cop_worker.rl.research_evaluation import (
    RecurrentResearchPolicy,
    ResearchPolicy,
    ScriptedResearchPolicy,
    evaluate_crossplay,
    evaluate_families,
    load_recurrent_network,
)
from cop_worker.rl.research_value_training import load_dqn_policy


def main() -> None:
    args = _build_parser().parse_args()
    base_checkpoint = torch.load(args.base, map_location="cpu", weights_only=True)
    network = load_recurrent_network(args.base, args.role)
    opponents = _population(args.role, args.incumbent_opponent)
    if args.teacher == "anti_loop":
        teachers: tuple[ResearchPolicy, ...] = tuple(
            ScriptedResearchPolicy(args.role, "anti_loop") for _ in opponents
        )
    elif args.teacher == "search_hybrid":
        teachers = tuple(
            RecurrentResearchPolicy(
                load_recurrent_network(args.base, args.role),
                args.role,
                temperature=0.5 if args.role == "thief" else None,
                search_strength=3.0,
                search_depth=1,
                search_particles=4,
            )
            for _ in opponents
        )
    elif args.teacher == "ddqn":
        if args.teacher_artifact is None:
            raise ValueError("--teacher-artifact is required for DDQN distillation")
        teachers = tuple(load_dqn_policy(args.teacher_artifact, args.role) for _ in opponents)
    elif args.role == "cop":
        oracle_names = (
            "anti_loop",
            "anti_loop",
            "anti_loop",
            "anti_loop",
            "scent_following",
            "targeted_exploit",
            "targeted_exploit",
            "scent_following",
            "wall",
            "local_adversarial_ensemble",
            "targeted_exploit",
            "anti_loop",
        )
        teachers = tuple(ScriptedResearchPolicy(args.role, name) for name in oracle_names)
    else:
        raise ValueError("population_oracle is currently defined only for cop")
    sequences = collect_teacher_sequences(
        teachers,
        args.role,
        args.incumbent_opponent,
        args.episodes,
        args.seed,
        args.random_start_fraction,
        RecurrentResearchPolicy(
            load_recurrent_network(args.base, args.role),
            args.role,
            temperature=0.5 if args.role == "thief" else None,
        )
        if args.preserve_random_base
        else None,
    )
    metrics = train_sequence_distillation(
        network,
        sequences,
        args.updates,
        args.seed + 1_000_000,
        args.learning_rate,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "role": args.role,
            "algorithm": "RecurrentA2C-GRU",
            "input_size": int(base_checkpoint["input_size"]),
            "n_actions": int(base_checkpoint["n_actions"]),
            "hidden_size": int(base_checkpoint["hidden_size"]),
            "training_steps": int(base_checkpoint["training_steps"])
            + sum(len(features) for features, _labels in sequences),
            "state_dict": network.state_dict(),
            "research_method": f"sequence distillation from {args.teacher}",
        },
        args.output,
    )
    opponent_role = "thief" if args.role == "cop" else "cop"
    incumbent_opponent = RecurrentResearchPolicy(
        load_recurrent_network(args.incumbent_opponent, opponent_role),
        opponent_role,
        temperature=0.5 if opponent_role == "thief" else None,
    )
    candidate = RecurrentResearchPolicy(
        network,
        args.role,
        temperature=0.5 if args.role == "thief" else None,
    )
    cop, thief = (
        (candidate, incumbent_opponent) if args.role == "cop" else (incumbent_opponent, candidate)
    )
    metrics.update(
        {
            "role": args.role,
            "teacher": args.teacher,
            "base_sha256": file_sha256(args.base),
            "artifact_sha256": file_sha256(args.output),
            "fixed_start_crossplay": evaluate_crossplay(
                cop, thief, 20, args.seed + 2_000_000, False
            ),
            "random_start_crossplay": evaluate_crossplay(
                cop, thief, 20, args.seed + 3_000_000, True
            ),
            "fixed_start_families": evaluate_families(
                candidate,
                args.role,
                incumbent_opponent,
                2,
                args.seed + 4_000_000,
                False,
            ),
        }
    )
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
