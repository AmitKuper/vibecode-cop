"""Paired A/B of two recurrent checkpoints under identical seeds.

Judges a candidate (e.g. a continuation fine-tune) against the deployed champion
using the canonical ``train_recurrent.evaluate`` tournament and its paired
bootstrap ``_promotion_comparison``. Same seed + same series => paired
series_results => valid bootstrap CI on the official-score difference.

Never overwrites weights or the manifest — read-only on both checkpoints.

Usage (from vibecode-cop repo root, PYTHONPATH=.):
  python scripts/rl_compare_two.py --role cop \
      --candidate /tmp/ft_cop/cop_recurrent_champion.pt \
      --baseline models/cop_recurrent_champion.pt \
      --historical models/thief_ppo_best.pt --series 15
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cop_worker.rl.policy_loader import load_checkpoint
from cop_worker.rl.train_recurrent import _promotion_comparison, evaluate
from scripts.rl_hybrid_eval import load_champion, summarise  # reuse loaders


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("cop", "thief"), required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--series", type=int, default=15)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--out", type=Path, default=Path("results/rl_compare_two.json"))
    args = parser.parse_args()

    temperature = args.temperature
    if temperature is None and args.role == "thief":
        temperature = 0.5

    opponent_role = "thief" if args.role == "cop" else "cop"
    historical = load_checkpoint(args.historical, opponent_role, max_steps=35)
    candidate = load_champion(args.candidate, args.role)
    baseline = load_champion(args.baseline, args.role)

    cand_eval = evaluate(candidate, args.role, args.series, args.seed, historical, temperature)
    base_eval = evaluate(baseline, args.role, args.series, args.seed, historical, temperature)
    promotion = _promotion_comparison(cand_eval, base_eval, args.seed)

    rows = [summarise("candidate", cand_eval), summarise("baseline", base_eval)]
    print(f"[compare] role={args.role} series/family={args.series} temp={temperature}")
    print(f"{'arm':<12}{'win_rate':>10}{'series_wr':>11}{'worst_fam_wr':>14}{'avg_turns':>11}")
    for r in rows:
        print(
            f"{r['arm']:<12}{r['win_rate']:>10.4f}{r['series_win_rate']:>11.4f}"
            f"{r['worst_family_win_rate']:>14.4f}{r['avg_turns']:>11.2f}"
        )
    print(
        f"\ncandidate - baseline win_rate delta = "
        f"{cand_eval['win_rate'] - base_eval['win_rate']:+.4f}"
    )
    print(f"mean series-score improvement = {promotion['mean_series_role_score_improvement']:+.3f}")
    print(
        f"paired bootstrap 95% CI = {promotion['bootstrap_95']}  "
        f"(significant improvement iff lower bound > 0)"
    )
    print(f"promotion gate passed = {promotion['passed']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "role": args.role,
                "series_per_family": args.series,
                "seed": args.seed,
                "temperature": temperature,
                "candidate_win_rate": cand_eval["win_rate"],
                "baseline_win_rate": base_eval["win_rate"],
                "win_rate_delta": cand_eval["win_rate"] - base_eval["win_rate"],
                "summaries": rows,
                "promotion": promotion,
                "candidate_families": {k: v["win_rate"] for k, v in cand_eval["families"].items()},
                "baseline_families": {k: v["win_rate"] for k, v in base_eval["families"].items()},
            },
            indent=2,
        )
    )
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
