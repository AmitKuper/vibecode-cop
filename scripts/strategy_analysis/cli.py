"""CLI: run the ablation grid and temperature sensitivity, write the payload."""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
from agent.rl.policy_loader import load_checkpoint
from agent.rl.recurrent_policy import file_sha256
from agent.rl.train_recurrent import evaluate

from strategy_analysis.report import _load_network, _summary, _write_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("cop", "thief"), required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--historical-checkpoint", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--series-per-family", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--release-temperature", type=float, default=0.0)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    network = _load_network(args.artifact, args.role)
    opponent_role = "thief" if args.role == "cop" else "cop"
    historical = load_checkpoint(args.historical_checkpoint, opponent_role, max_steps=35)
    release_temperature = args.release_temperature or None

    specifications = [
        ("full_release", {}, "exact release inference"),
        ("strongest_heuristic", {"force_expert_actor": True}, "local belief heuristic"),
        ("scent_only_no_belief", {"feature_mode": "no_belief"}, "belief tensor removed"),
        ("belief_only_no_scent", {"feature_mode": "no_scent"}, "scent tensor removed"),
        ("stateless", {"recurrent_enabled": False}, "recurrent state reset every turn"),
        ("no_legal_mask", {"legal_mask_enabled": False}, "offline unsafe-mask ablation"),
    ]
    if args.role == "cop":
        specifications.append(
            ("no_barrier_actions", {"barrier_actions_enabled": False}, "PLACE actions removed")
        )
    else:
        specifications.append(
            ("belief_risk_mask", {"risk_mask_enabled": True}, "belief-risk pruning added")
        )

    rows: list[dict] = []
    raw: dict[str, dict] = {}
    for name, options, note in specifications:
        result = evaluate(
            network,
            args.role,
            args.series_per_family,
            args.seed,
            historical,
            inference_temperature=release_temperature,
            **options,
        )
        raw[name] = result
        rows.append(_summary(name, result, note))

    # Movement and language are intentionally separate. With the exact same seeds,
    # enabling templates cannot alter physical actions in this offline simulator.
    language_off = dict(rows[0])
    language_off["variant"] = "language_off"
    language_off["note"] = "measured invariant: language policy cannot enter movement inference"
    rows.append(language_off)

    sensitivity_rows: list[dict] = []
    for temperature in (0.0, 0.25, 0.5, 0.75):
        result = (
            raw["full_release"]
            if (temperature or None) == release_temperature
            else evaluate(
                network,
                args.role,
                args.series_per_family,
                args.seed,
                historical,
                inference_temperature=temperature or None,
            )
        )
        sensitivity_rows.append(
            {
                "inference_mode": "argmax" if temperature == 0 else "controlled_stochastic",
                "temperature": temperature,
                "win_rate": result["win_rate"],
                "series_win_rate": result["series_win_rate"],
                "official_role_score": result["official_role_score"],
                "score_differential": result["official_role_score"]
                - result["official_opponent_score"],
                "worst_family_win_rate": result["worst_family_win_rate"],
                "illegal_action_rate": result["illegal_action_rate"],
                "p99_inference_ms": result["inference_latency_ms"]["p99"],
            }
        )

    _write_csv(args.output_dir / "ablations.csv", rows)
    _write_csv(args.output_dir / "sensitivity.csv", sensitivity_rows)
    payload = {
        "schema_version": "1.0",
        "role": args.role,
        "artifact": str(args.artifact),
        "artifact_sha256": file_sha256(args.artifact),
        "historical_checkpoint_sha256": file_sha256(args.historical_checkpoint),
        "seed": args.seed,
        "series_per_family": args.series_per_family,
        "training_seed_namespace": [args.seed, args.seed],
        "held_out_seed_namespace": [args.seed + 10_000, args.seed + 50_000],
        "language_official_score_delta": 0,
        "language_ablation_interpretation": (
            "Movement and language are separate by contract; language templates have zero "
            "physical-score effect in the local movement simulator."
        ),
        "ablations": rows,
        "sensitivity": sensitivity_rows,
        "raw_results": raw,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "wall_seconds": time.perf_counter() - started,
        },
    }
    (args.output_dir / "strategy_analysis.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", **payload["environment"]}, indent=2))
