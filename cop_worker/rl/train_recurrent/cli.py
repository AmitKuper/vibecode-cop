"""Command-line entry point: train (or evaluate) and write the evidence artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

import cop_worker.rl.train_recurrent as _pkg
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import obs_tensor_shape
from cop_worker.rl.recurrent_policy import RecurrentActorCritic, file_sha256
from cop_worker.rl.train_recurrent.cli_helpers import (
    _annotate_evaluation,
    _load_historical_policy,
)
from cop_worker.rl.train_recurrent.schedules import FAMILIES


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("cop", "thief"), required=True)
    parser.add_argument("--episodes", type=int, default=1200)
    parser.add_argument("--eval-series-per-family", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--models-dir", type=Path, default=Path("models"))
    parser.add_argument("--evidence-dir", type=Path, default=Path("results"))
    parser.add_argument("--historical-checkpoint", type=Path, required=False, default=None)
    parser.add_argument("--inference-temperature", type=float, default=0.0)
    parser.add_argument("--evaluate-only-artifact", type=Path)
    parser.add_argument("--resume-artifact", type=Path)
    parser.add_argument("--resume-learning-rate", type=float, default=3e-4)
    parser.add_argument("--resume-expert-probability", type=float, default=0.0)
    parser.add_argument("--resume-imitation-weight", type=float, default=0.0)
    parser.add_argument("--training-families", nargs="+", choices=FAMILIES)
    parser.add_argument("--grid-size", type=int, default=7)
    parser.add_argument(
        "--fixed-start-fraction",
        type=float,
        default=0.0,
        help="Fraction of training episodes started from the SIGNED match "
        "start (cop_start/thief_start) instead of random cells",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    args.models_dir.mkdir(parents=True, exist_ok=True)
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    opponent_role = "thief" if args.role == "cop" else "cop"
    historical_policy = _load_historical_policy(args, opponent_role)
    resumed_from_sha256 = None
    if args.evaluate_only_artifact:
        artifact = args.evaluate_only_artifact
        checkpoint = torch.load(artifact, map_location="cpu", weights_only=True)
        if checkpoint.get("role") != args.role:
            raise RuntimeError("evaluation artifact role does not match --role")
        network = RecurrentActorCritic(
            int(checkpoint["input_size"]),
            int(checkpoint["n_actions"]),
            int(checkpoint["hidden_size"]),
        )
        network.load_state_dict(checkpoint["state_dict"])
        network.eval()
        training_episodes = int(checkpoint["training_steps"]) // 35
    else:
        resume_checkpoint = None
        previous_training_steps = 0
        if args.resume_artifact:
            resumed_from_sha256 = file_sha256(args.resume_artifact)
            resume_checkpoint = torch.load(
                args.resume_artifact, map_location="cpu", weights_only=True
            )
            previous_training_steps = int(resume_checkpoint["training_steps"])
        network = _pkg.train(
            args.role,
            args.episodes,
            args.seed,
            args.hidden_size,
            historical_policy,
            resume_checkpoint,
            args.resume_learning_rate,
            args.resume_expert_probability,
            args.resume_imitation_weight,
            tuple(args.training_families) if args.training_families else None,
            grid_size=args.grid_size,
            fixed_start_fraction=args.fixed_start_fraction,
        )
        artifact_name = f"{args.role}_recurrent_champion.pt"
        artifact = args.models_dir / artifact_name
        torch.save(
            {
                "role": args.role,
                "algorithm": "RecurrentA2C-GRU",
                "input_size": obs_tensor_shape(args.grid_size),
                "n_actions": len(COP_ACTIONS if args.role == "cop" else THIEF_ACTIONS),
                "hidden_size": args.hidden_size,
                "training_steps": previous_training_steps + args.episodes * 35,
                "state_dict": network.state_dict(),
            },
            artifact,
        )
        training_episodes = (previous_training_steps // 35) + args.episodes
    inference_temperature = args.inference_temperature or None
    if inference_temperature is not None and not 0 < inference_temperature <= 1:
        raise RuntimeError("inference temperature must be in (0, 1]")
    evaluation = _pkg.evaluate(
        network,
        args.role,
        args.eval_series_per_family,
        args.seed,
        historical_policy,
        inference_temperature,
        grid_size=args.grid_size,
    )
    heuristic_baseline = _pkg.evaluate(
        network,
        args.role,
        args.eval_series_per_family,
        args.seed,
        historical_policy,
        force_expert_actor=True,
        grid_size=args.grid_size,
    )
    promotion = _pkg._promotion_comparison(evaluation, heuristic_baseline, args.seed)
    _annotate_evaluation(evaluation, args, artifact, training_episodes, resumed_from_sha256)
    evaluation["strongest_heuristic_baseline"] = heuristic_baseline
    evaluation["promotion_gate"] = promotion
    evidence = args.evidence_dir / f"{args.role}_held_out_tournament.json"
    evidence.write_text(json.dumps(evaluation, indent=2))
    print(json.dumps({"artifact": str(artifact), "evaluation": evaluation}, indent=2))
