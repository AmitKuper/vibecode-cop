"""Matched-seed A/B evaluation of champion RL vs greedy vs hybrid policies.

Reuses the *canonical* held-out tournament from ``train_recurrent.evaluate`` so
the methodology (families, seeds, six-gamelet series, scoring) is identical to
the promotion gate used on ``main``. This script never trains, never edits the
trainer, and never overwrites champion weights or the manifest.

Arms (all under identical seeds and identical scripted/historical opponents):
  * champion : the deployed RecurrentActorCritic, inference mode per manifest
  * greedy   : force_expert_actor=True (pure belief pursuit/evasion teacher)
  * hybrid-* : champion wrapped in HybridActorCritic (confidence-gated greedy)

Usage (from the vibecode-cop repo root):
  .venv/Scripts/python.exe scripts/rl_hybrid_eval.py --role cop \
      --champion models/cop_recurrent_champion.pt \
      --historical models/thief_ppo_best.pt --series 8
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from cop_worker.rl.hybrid_policy import HybridActorCritic
from cop_worker.rl.policy_loader import load_checkpoint
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.train_recurrent import _promotion_comparison, evaluate

# (strength, conf_threshold) grid for the confidence-gated hybrid sweep.
HYBRID_GRID = [(0.5, 0.0), (1.0, 0.0), (2.0, 0.0), (1.0, 0.3), (2.0, 0.3), (2.0, 0.5)]


def load_champion(path: Path, role: str) -> RecurrentActorCritic:
    """Rebuild the deployed recurrent network from a champion checkpoint."""
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint.get("role") != role:
        raise RuntimeError(f"champion role {checkpoint.get('role')!r} != {role!r}")
    network = RecurrentActorCritic(
        int(checkpoint["input_size"]),
        int(checkpoint["n_actions"]),
        int(checkpoint["hidden_size"]),
    )
    network.load_state_dict(checkpoint["state_dict"])
    return network.eval()


def summarise(name: str, result: dict) -> dict:
    """Extract the headline metrics from a tournament result dict."""
    worst = min(result["families"].items(), key=lambda kv: kv[1]["win_rate"])
    return {
        "arm": name,
        "win_rate": round(result["win_rate"], 4),
        "series_win_rate": round(result["series_win_rate"], 4),
        "worst_family": worst[0],
        "worst_family_win_rate": round(worst[1]["win_rate"], 4),
        "avg_turns": round(result["average_turns"], 2),
        "illegal_action_rate": result["illegal_action_rate"],
        "official_role_score": result["official_role_score"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("cop", "thief"), required=True)
    parser.add_argument("--champion", type=Path, required=True)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--series", type=int, default=8, help="series per family")
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="inference temperature; default per role (thief=0.5)",
    )
    parser.add_argument("--out", type=Path, default=Path("results/rl_hybrid_eval.json"))
    args = parser.parse_args()

    temperature = args.temperature
    if temperature is None and args.role == "thief":
        temperature = 0.5  # matches thief champion manifest inference_mode=low_temp

    opponent_role = "thief" if args.role == "cop" else "cop"
    historical = load_checkpoint(args.historical, opponent_role, max_steps=35)
    champion = load_champion(args.champion, args.role)

    def run(network) -> dict:
        return evaluate(network, args.role, args.series, args.seed, historical, temperature)

    print(f"[eval] role={args.role} series/family={args.series} temp={temperature}")
    arms: dict[str, dict] = {}
    arms["champion"] = run(champion)
    arms["greedy"] = evaluate(
        champion,
        args.role,
        args.series,
        args.seed,
        historical,
        temperature,
        force_expert_actor=True,
    )
    for strength, threshold in HYBRID_GRID:
        wrapped = HybridActorCritic(
            champion, args.role, strength=strength, conf_threshold=threshold
        )
        arms[f"hybrid_s{strength}_c{threshold}"] = run(wrapped)

    summaries = [summarise(name, res) for name, res in arms.items()]
    champ_wr = arms["champion"]["win_rate"]
    best_name, best = max(arms.items(), key=lambda kv: kv[1]["win_rate"])
    promotion = _promotion_comparison(best, arms["champion"], args.seed)

    print(f"\n{'arm':<22}{'win_rate':>10}{'series_wr':>11}{'worst_fam_wr':>14}{'avg_turns':>11}")
    for s in summaries:
        print(
            f"{s['arm']:<22}{s['win_rate']:>10.4f}{s['series_win_rate']:>11.4f}"
            f"{s['worst_family_win_rate']:>14.4f}{s['avg_turns']:>11.2f}"
        )
    print(f"\nchampion win_rate = {champ_wr:.4f}")
    print(f"best arm          = {best_name} @ {best['win_rate']:.4f}")
    print(
        f"paired promotion vs champion: passed={promotion['passed']} "
        f"mean_score_delta={promotion['mean_series_role_score_improvement']:.3f} "
        f"bootstrap95={promotion['bootstrap_95']}"
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "role": args.role,
                "series_per_family": args.series,
                "seed": args.seed,
                "temperature": temperature,
                "champion_win_rate": champ_wr,
                "best_arm": best_name,
                "summaries": summaries,
                "best_vs_champion_promotion": promotion,
            },
            indent=2,
        )
    )
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
