"""CLI helpers: historical-policy loading and evidence annotation."""

from __future__ import annotations

import pickle

import torch

from cop_worker.rl.local_obs_adapter import obs_tensor_shape
from cop_worker.rl.recurrent_policy import RecurrentActorCritic, file_sha256
from cop_worker.rl.train_recurrent.schedules import (
    COP_TRAINING_SCHEDULE,
    FAMILIES,
    THIEF_TRAINING_SCHEDULE,
)


def _load_historical_policy(args, opponent_role: str):
    if args.historical_checkpoint is None:
        return None
    try:
        _raw_ckpt = torch.load(args.historical_checkpoint, map_location="cpu", weights_only=True)
    except (EOFError, KeyError, RuntimeError, pickle.UnpicklingError):
        _raw_ckpt = None
    if isinstance(_raw_ckpt, dict) and {
        "state_dict",
        "input_size",
    }.issubset(_raw_ckpt):
        _hist_net = RecurrentActorCritic(
            int(_raw_ckpt["input_size"]),
            int(_raw_ckpt["n_actions"]),
            int(_raw_ckpt["hidden_size"]),
        )
        _hist_net.load_state_dict(_raw_ckpt["state_dict"])
        return _hist_net.eval()
    from cop_worker.rl.policy_loader import load_checkpoint

    _old_policy = load_checkpoint(args.historical_checkpoint, opponent_role, max_steps=35)
    expected_input = obs_tensor_shape(args.grid_size)
    try:
        _old_input = _old_policy.net.backbone.net[0].weight.shape[1]
    except Exception:
        _old_input = expected_input
    return _old_policy if _old_input == expected_input else None


def _annotate_evaluation(
    evaluation: dict,
    args,
    artifact,
    training_episodes: int,
    resumed_from_sha256,
) -> None:
    """Attach provenance fields the evidence artifact must carry."""
    evaluation["artifact_sha256"] = file_sha256(artifact)
    evaluation["evaluation_seed"] = args.seed
    evaluation["training_seed_namespace"] = [args.seed, args.seed + args.episodes]
    evaluation["held_out_seed_namespace"] = [args.seed + 10_000, args.seed + 50_000]
    evaluation["training_episodes"] = training_episodes
    evaluation["training_opponents"] = list(FAMILIES)
    evaluation["training_schedule"] = list(
        args.training_families
        or (THIEF_TRAINING_SCHEDULE if args.role == "thief" else COP_TRAINING_SCHEDULE)
    )
    evaluation["historical_checkpoint"] = (
        str(args.historical_checkpoint) if args.historical_checkpoint else None
    )
    evaluation["historical_checkpoint_sha256"] = (
        file_sha256(args.historical_checkpoint) if args.historical_checkpoint else None
    )
    evaluation["demonstration_episodes"] = 240
    evaluation["imitation_updates"] = 600
    evaluation["training_method"] = "local-belief BC warm start + recurrent A2C"
    if not args.evaluate_only_artifact:
        evaluation["resumed_from_sha256"] = resumed_from_sha256
        if args.resume_artifact:
            evaluation["resume_hyperparams"] = {
                "learning_rate": args.resume_learning_rate,
                "expert_probability": args.resume_expert_probability,
                "imitation_weight": args.resume_imitation_weight,
            }
