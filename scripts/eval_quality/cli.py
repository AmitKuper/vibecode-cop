"""CLI: trace, 2x2 belief x scent ablation, and deployed head-to-head."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_quality.deployed import DeployedPolicy
from eval_quality.game import move_stats, play
from eval_quality.suites import suite


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=30, help="games per opponent family")
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--trace", action="store_true", help="print an annotated sample game")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    report: dict = {"seed": args.seed, "games_per_family": args.games, "suites": []}

    if args.trace:
        cop = DeployedPolicy("cop", "prod")
        thief = DeployedPolicy("thief", "prod")
        tr: list = []
        winner, turns = play(cop, thief, args.seed, 1, trace=tr)
        print(f"\n=== deployed cop vs deployed thief (gamelet 1) -> {winner} @ {turns} ===")
        print(
            f"{'st':>3} {'cop':>7} {'act':>7} -> {'to':>7} | "
            f"{'thief':>7} {'act':>5} -> {'to':>7} | cheb"
        )
        for t in tr:
            print(
                f"{t['step']:>3} {str(t['cop_from']):>7} {t['cop_action']:>7} -> "
                f"{str(t['cop_to']):>7} | {str(t['thief_from']):>7} "
                f"{t['thief_action']:>5} -> {str(t['thief_to']):>7} | {t['chebyshev']}"
            )
        print("\ncop  move-stats:", json.dumps(move_stats(tr, "cop")))
        print("thief move-stats:", json.dumps(move_stats(tr, "thief")))
        report["sample_trace"] = {"winner": winner, "turns": turns, "steps": tr}
        report["sample_move_stats"] = {
            "cop": move_stats(tr, "cop"),
            "thief": move_stats(tr, "thief"),
        }

    # 2x2 ablation: belief (uniform vs live) x scent (trainer's unclamped vs wire-clamped).
    # "prod + wire" is what a real counted match actually feeds the nets today.
    for role in ("cop", "thief"):
        for scent_mode in ("train", "wire"):
            for belief_mode in ("prod", "live"):
                res = suite(role, belief_mode, args.games, args.seed, scent_mode)
                report["suites"].append(res)
                tag = (
                    "  <-- REAL PRODUCTION" if (scent_mode, belief_mode) == ("wire", "prod") else ""
                )
                print(
                    f"\n[{role} / belief={belief_mode} / scent={scent_mode}] "
                    f"overall={res['overall_win_rate']:.3f} over {res['games']} games{tag}"
                )
                for fam, m in res["per_family"].items():
                    print(f"    {fam:<28} win={m['win_rate']:.2f}  avg_turns={m['avg_turns']}")

    # Head-to-head, both as deployed, on the real wire scent.
    report["head_to_head_deployed"] = {}
    for scent_mode in ("train", "wire"):
        h2h = {"cop_wins": 0, "games": args.games}
        cop_p, thief_p = DeployedPolicy("cop", "prod"), DeployedPolicy("thief", "prod")
        for i in range(args.games):
            winner, _ = play(
                cop_p, thief_p, args.seed + i * 7919, (i % 6) + 1, scent_mode=scent_mode
            )
            h2h["cop_wins"] += int(winner == "cop")
        h2h["cop_win_rate"] = round(h2h["cop_wins"] / args.games, 3)
        report["head_to_head_deployed"][scent_mode] = h2h
        print(
            f"\n[head-to-head, both deployed, scent={scent_mode}] "
            f"cop_win_rate={h2h['cop_win_rate']:.3f}"
        )

    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
